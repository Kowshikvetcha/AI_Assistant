"""
FastAPI application — main entry point for the interview helper backend.

Orchestrates: audio capture → STT → LLM → WebSocket broadcast.
"""

import asyncio
import time
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from config import get_settings
from models import (
    MessageType,
    StatusMessage,
    ErrorMessage,
    PerformanceMetrics,
    TranscriptMessage,
    ChatRequest,
    ScreenCaptureRequest,
)
from websocket_manager import ConnectionManager, parse_control_message
from audio_capture import capture_system_audio
from stt import transcribe_audio
from llm import generate_answer, summarize_context
from resume_parser import parse_resume
from screen_capture import extract_text_from_image
from utils import setup_logging, encode_wav, is_silent, perf_timer

# ── Globals ──────────────────────────────────────────────────────────
settings = get_settings()
logger = setup_logging(settings.LOG_LEVEL)
manager = ConnectionManager()

# Startup warnings collected during lifespan — sent to each new WS client
_startup_errors: list[str] = []

# Pipeline state
_capture_task: asyncio.Task | None = None
_is_capturing = False
_resume_context: str = ""
_resume_filename: str = ""
_clear_memory_event = asyncio.Event()
QUESTION_START_PHRASES = (
    "what", "why", "how", "when", "where", "who", "which",
    "can", "could", "would", "should", "do", "does", "did",
    "is", "are", "was", "were", "explain", "compare", "difference between",
    "tell", "describe", "walk", "name", "list", "give", "share",
    "talk", "discuss", "elaborate", "define", "demonstrate",
)
CONTINUATION_PREFIXES = (
    "and ", "or ", "also ", "then ", "so ", "but ",
    "because ", "while ", "with ", "of ", "to ", "for ", "in ",
)
TRAILING_INCOMPLETE_TOKENS = {
    "and", "or", "to", "of", "for", "with", "between", "vs", "versus",
    "the", "a", "an",
}
MIN_WORDS_WITH_QMARK = 3
MIN_WORDS_NO_QMARK_QUESTION_START = 4
MIN_WORDS_NO_QMARK_GENERIC = 5
QUEUE_POLL_TIMEOUT_SECONDS = 0.4
PAUSE_TRIGGER_SECONDS = 1.2
MAX_INCOMPLETE_HOLD_SECONDS = 3.0


# ── Lifespan ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _startup_errors
    logger.info("🚀 Interview Helper backend starting...")
    logger.info(f"   Port:  {settings.WEBSOCKET_PORT}")

    # Validate required configuration up-front so users see clear errors
    # instead of silent failures buried deep in the pipeline.
    try:
        logger.info(f"   Provider: {settings.provider}")
        logger.info(f"   LLM model: {settings.llm_model}")
        logger.info(f"   Summary model: {settings.summary_model}")
        logger.info(f"   STT model: {settings.stt_model}")
        _ = settings.api_key  # Raises ValueError if missing
        logger.info("   API key: configured ✓")
    except ValueError as e:
        msg = (
            f"Configuration error: {e}. "
            "Create a .env file in the project root with AI_API_KEY=your_key. "
            "See .env.example for all options."
        )
        logger.error(f"❌ {msg}")
        _startup_errors.append(msg)
    except Exception as e:
        msg = f"Unexpected startup error: {e}"
        logger.error(f"❌ {msg}")
        _startup_errors.append(msg)

    yield
    # Shutdown — cancel capture if running
    await stop_capture()
    logger.info("👋 Backend shut down.")


# ── App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Interview Helper API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global error handlers ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "error": "An unexpected server error occurred. Check the backend logs."},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = "; ".join(f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in exc.errors())
    return JSONResponse(
        status_code=422,
        content={"status": "error", "error": f"Invalid request: {errors}"},
    )


# ── Health ───────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "capturing": _is_capturing,
        "clients": manager.client_count,
        "resume_loaded": bool(_resume_context),
    }


# ── Resume Upload ────────────────────────────────────────────────────
@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """Upload a resume (PDF or TXT) to provide candidate context to the LLM."""
    global _resume_context, _resume_filename
    try:
        file_bytes = await file.read()
        _resume_context = parse_resume(file_bytes, file.filename or "resume.txt")
        _resume_filename = file.filename or "resume"
        logger.info(f"📄 Resume loaded: {_resume_filename} ({len(_resume_context)} chars)")

        await manager.broadcast(
            StatusMessage(
                status="resume_loaded",
                detail=f"Resume loaded: {_resume_filename}",
            ).model_dump()
        )

        return {
            "status": "ok",
            "filename": _resume_filename,
            "chars": len(_resume_context),
        }
    except ValueError as e:
        logger.warning(f"⚠️  Resume upload failed: {e}")
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error(f"❌ Resume upload error: {e}")
        return {"status": "error", "error": "Failed to process resume file."}


@app.get("/resume-status")
async def resume_status():
    """Check if a resume is currently loaded."""
    return {
        "loaded": bool(_resume_context),
        "filename": _resume_filename if _resume_context else None,
        "chars": len(_resume_context) if _resume_context else 0,
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    """Answer a manually typed user question via the same LLM pipeline."""
    question = request.question.strip()
    if not question:
        return {"status": "error", "error": "Question cannot be empty."}

    try:
        llm_resp, _, _ = await generate_answer(
            transcript=question,
            api_key=settings.api_key,
            model=settings.llm_model,
            max_tokens=settings.LLM_MAX_TOKENS,
            interview_summary="",
            resume_context=_resume_context,
            base_url=settings.base_url,
        )
        return llm_resp.model_dump()
    except RuntimeError as e:
        logger.error(f"❌ Chat LLM error: {e}")
        return {"status": "error", "error": f"LLM error: {e}"}
    except Exception as e:
        logger.error(f"❌ Chat endpoint error: {e}")
        return {"status": "error", "error": "Failed to process chat request."}


# ── Screen Capture OCR ──────────────────────────────────────────────
@app.post("/capture-screen")
async def capture_screen(request: ScreenCaptureRequest):
    """Extract text from a screenshot via OCR. Returns the text for user review."""
    import base64

    try:
        image_bytes = base64.b64decode(request.image)
    except Exception:
        return {"status": "error", "error": "Invalid base64 image data."}

    # Run OCR in a thread to avoid blocking the event loop
    try:
        extracted_text = await asyncio.to_thread(extract_text_from_image, image_bytes)
    except RuntimeError as e:
        logger.error(f"OCR error: {e}")
        return {"status": "error", "error": str(e)}

    if not extracted_text:
        return {"status": "error", "error": "No text could be extracted from the image."}

    logger.info(f"OCR extracted {len(extracted_text)} chars from screenshot")
    return {"status": "ok", "text": extracted_text}


# ── Audio → STT → LLM pipeline (producer/consumer) ─────────────────
_audio_queue: asyncio.Queue | None = None


async def _audio_producer():
    """Continuously capture audio chunks into the queue. Never blocks on processing."""
    global _is_capturing
    try:
        async for audio_chunk in capture_system_audio(
            chunk_duration=settings.AUDIO_CHUNK_DURATION
        ):
            if not _is_capturing:
                break

            # Skip silent chunks
            if is_silent(audio_chunk, threshold=0.005):
                continue

            # Pre-encode to WAV immediately (fast, CPU-only)
            wav_bytes = encode_wav(audio_chunk)

            # Put into queue (drop oldest if queue is full to avoid memory buildup)
            if _audio_queue.full():
                try:
                    _audio_queue.get_nowait()
                    logger.warning("⚠️  Dropped oldest audio chunk (processing too slow)")
                except asyncio.QueueEmpty:
                    pass
            await _audio_queue.put(wav_bytes)

    except asyncio.CancelledError:
        raise  # Normal shutdown — let it propagate
    except Exception as e:
        logger.error(f"Audio producer error: {e}")
        # Broadcast to the UI so users see the real error message
        await manager.broadcast(
            ErrorMessage(error=str(e), recoverable=False).model_dump()
        )
        _is_capturing = False  # Signal the consumer to stop cleanly


async def _audio_consumer():
    """Process audio chunks from the queue: STT → broadcast → debounced LLM."""
    active_question_buffer: list[str] = []
    summary_buffer: list[str] = []
    interview_summary: str = ""
    silence_elapsed = 0.0
    _llm_task: asyncio.Task | None = None

    def _should_trigger_question_boundary(latest_chunk: str) -> bool:
        latest = latest_chunk.strip()
        if not latest:
            return False
        return "?" in latest

    def _looks_incomplete_question(assembled_text: str) -> bool:
        text = assembled_text.strip().lower()
        if not text:
            return True
        words = text.split()
        word_count = len(words)
        starts_like_question = text.startswith(QUESTION_START_PHRASES)
        has_qmark = "?" in text

        if has_qmark:
            return word_count < MIN_WORDS_WITH_QMARK

        # A sentence ending with a period is almost certainly complete.
        if text.endswith(".") and word_count >= 3:
            return False

        # Without '?', be stricter so we avoid sending partial fragments.
        if starts_like_question and word_count < MIN_WORDS_NO_QMARK_QUESTION_START:
            return True
        if not starts_like_question and word_count < MIN_WORDS_NO_QMARK_GENERIC:
            return True
        if text.startswith(CONTINUATION_PREFIXES):
            return True
        # Trailing connectors usually indicate the question is cut mid-sentence.
        last_token = re.sub(r"[^a-z0-9]+$", "", words[-1]) if words else ""
        if last_token in TRAILING_INCOMPLETE_TOKENS:
            return True
        if text.endswith((",", ":", "-", ";")):
            return True
        return False

    while _is_capturing:
        try:
            if _clear_memory_event.is_set():
                active_question_buffer.clear()
                summary_buffer.clear()
                interview_summary = ""
                silence_elapsed = 0.0
                if _llm_task and not _llm_task.done():
                    _llm_task.cancel()
                _clear_memory_event.clear()
                logger.info("Conversation memory cleared")

            # Wait for next audio chunk (with timeout to check _is_capturing)
            try:
                wav_bytes = await asyncio.wait_for(
                    _audio_queue.get(), timeout=QUEUE_POLL_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                # Timeout = speech pause → trigger LLM if we have new transcripts
                if active_question_buffer:
                    combined_text = " ".join(active_question_buffer).strip()
                    if not combined_text:
                        continue
                    silence_elapsed += QUEUE_POLL_TIMEOUT_SECONDS
                    if _looks_incomplete_question(combined_text):
                        if silence_elapsed >= MAX_INCOMPLETE_HOLD_SECONDS:
                            logger.info(
                                "Dropping stale incomplete question after long silence"
                            )
                            active_question_buffer.clear()
                            silence_elapsed = 0.0
                        logger.info("Skipping LLM trigger on pause (question looks incomplete)")
                        continue
                    if silence_elapsed < PAUSE_TRIGGER_SECONDS:
                        continue
                    # Cancel previous LLM if still running
                    if _llm_task and not _llm_task.done():
                        _llm_task.cancel()
                    _llm_task = asyncio.create_task(
                        _process_llm(combined_text, 0, interview_summary, _resume_context)
                    )
                    active_question_buffer.clear()
                    silence_elapsed = 0.0
                    logger.info("🧠 LLM triggered (speech pause)")
                continue

            # ── STT ──────────────────────────────────────────────
            try:
                transcript, stt_latency = await transcribe_audio(
                    wav_bytes,
                    api_key=settings.api_key,
                    model=settings.stt_model,
                    base_url=settings.base_url,
                )
            except RuntimeError as e:
                logger.error(f"❌ STT error: {e}")
                await manager.broadcast(
                    ErrorMessage(
                        error=f"STT error: {e}", recoverable=True
                    ).model_dump()
                )
                continue

            if not transcript:
                continue

            # Filter Whisper hallucinations
            cleaned = transcript.lower().strip().rstrip(".!,")
            HALLUCINATION_PHRASES = {
                "you", "thank you", "thanks", "bye", "goodbye",
                "thank you for watching", "thanks for watching",
                "subscribe", "like and subscribe",
                "the end", "...",
            }
            if cleaned in HALLUCINATION_PHRASES or len(transcript.strip()) < 4:
                continue

            logger.info(f"📝 Transcript ({stt_latency:.0f}ms): {transcript[:80]}")

            # Broadcast transcript immediately (live feed)
            ts_msg = TranscriptMessage(
                text=transcript,
                timestamp=time.time(),
                latency_ms=stt_latency,
            )
            await manager.broadcast(ts_msg.model_dump())

            # Accumulate context for LLM
            active_question_buffer.append(transcript)
            summary_buffer.append(transcript)
            silence_elapsed = 0.0
            assembled_question = " ".join(active_question_buffer).strip()

            # ── Two-Tier Memory Management ──────────────────────
            # If buffer gets too large (>10 chunks / ~20s), compress oldest chunks
            if len(summary_buffer) >= 10:
                # Take oldest 5 chunks to summarize
                to_summarize = " ".join(summary_buffer[:5])
                # Keep newest chunks in buffer
                summary_buffer = summary_buffer[5:]
                
                # Update summary (async, may block consumer briefly but queue handles it)
                interview_summary = await summarize_context(
                    old_summary=interview_summary,
                    new_text=to_summarize,
                    api_key=settings.api_key,
                    model=settings.summary_model,
                    base_url=settings.base_url,
                )

            # Trigger quickly when interviewer likely finished a question.
            if active_question_buffer and _should_trigger_question_boundary(transcript):
                if _looks_incomplete_question(assembled_question):
                    logger.info("Ignoring boundary trigger (question looks incomplete)")
                    continue
                combined_text = assembled_question
                if _llm_task and not _llm_task.done():
                    _llm_task.cancel()
                _llm_task = asyncio.create_task(
                    _process_llm(combined_text, stt_latency, interview_summary, _resume_context)
                )
                active_question_buffer.clear()
                silence_elapsed = 0.0
                logger.info("LLM triggered (question boundary)")
                continue

        except Exception as e:
            logger.error(f"Consumer error: {e}")
            continue


async def _process_llm(
    combined_text: str, 
    stt_latency: float, 
    interview_summary: str = "",
    resume_context: str = "",
):
    """Run LLM in background so it doesn't block the STT pipeline."""
    try:
        llm_resp, llm_latency, tokens = await generate_answer(
            transcript=combined_text,
            api_key=settings.api_key,
            model=settings.llm_model,
            max_tokens=settings.LLM_MAX_TOKENS,
            interview_summary=interview_summary,
            resume_context=resume_context,
            base_url=settings.base_url,
        )
        await manager.broadcast(llm_resp.model_dump())

        metrics = PerformanceMetrics(
            stt_latency_ms=stt_latency,
            llm_latency_ms=llm_latency,
            total_latency_ms=stt_latency + llm_latency,
            tokens_used=tokens,
            timestamp=time.time(),
        )
        logger.info(
            f"📊 Cycle: STT={metrics.stt_latency_ms:.0f}ms, "
            f"LLM={metrics.llm_latency_ms:.0f}ms, "
            f"Total={metrics.total_latency_ms:.0f}ms, "
            f"Tokens={metrics.tokens_used}"
        )
    except RuntimeError as e:
        await manager.broadcast(
            ErrorMessage(
                error=f"LLM error: {e}", recoverable=True
            ).model_dump()
        )


async def processing_pipeline():
    """Main pipeline: runs producer and consumer concurrently."""
    global _is_capturing, _audio_queue
    _is_capturing = True
    _audio_queue = asyncio.Queue(maxsize=10)

    await manager.broadcast(
        StatusMessage(
            status="capturing", detail="Audio capture started"
        ).model_dump()
    )

    try:
        # Run producer and consumer concurrently
        await asyncio.gather(
            _audio_producer(),
            _audio_consumer(),
        )
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        await manager.broadcast(
            ErrorMessage(
                error=f"Pipeline stopped: {e}", recoverable=False
            ).model_dump()
        )
    finally:
        _is_capturing = False
        await manager.broadcast(
            StatusMessage(
                status="stopped", detail="Audio capture stopped"
            ).model_dump()
        )


async def start_capture():
    """Start the audio capture pipeline."""
    global _capture_task, _is_capturing
    if _is_capturing:
        logger.info("Capture already running.")
        return

    # Pre-flight: verify API key before starting the pipeline so users get
    # a clear error immediately instead of silent failures mid-transcription.
    try:
        _ = settings.api_key
    except ValueError as e:
        await manager.broadcast(
            ErrorMessage(
                error=(
                    f"Cannot start: {e}. "
                    "Add AI_API_KEY=your_key to the .env file and restart the backend."
                ),
                recoverable=False,
            ).model_dump()
        )
        return

    _capture_task = asyncio.create_task(processing_pipeline())
    logger.info("▶️  Capture pipeline started.")


async def stop_capture():
    """Stop the audio capture pipeline."""
    global _capture_task, _is_capturing
    _is_capturing = False
    if _capture_task and not _capture_task.done():
        _capture_task.cancel()
        try:
            await _capture_task
        except asyncio.CancelledError:
            pass
    _capture_task = None
    logger.info("⏹  Capture pipeline stopped.")


# ── WebSocket endpoint ───────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for frontend communication."""
    await manager.connect(websocket)

    # Send initial status
    await manager.send_personal(
        websocket,
        StatusMessage(
            status="connected",
            detail=f"Capturing: {_is_capturing}",
        ).model_dump(),
    )

    # Replay any startup configuration errors so the user sees them immediately
    for err in _startup_errors:
        await manager.send_personal(
            websocket,
            ErrorMessage(error=err, recoverable=False).model_dump(),
        )

    try:
        while True:
            data = await websocket.receive_text()
            control = await parse_control_message(data)

            if control is None:
                await manager.send_personal(
                    websocket,
                    ErrorMessage(
                        error="Invalid message format", recoverable=True
                    ).model_dump(),
                )
                continue

            if control.action == "start":
                await start_capture()
            elif control.action == "stop":
                await stop_capture()
            elif control.action == "clear":
                logger.info("🗑  Transcript buffer cleared by client.")
                await manager.broadcast(
                    StatusMessage(
                        status="cleared", detail="Transcript cleared"
                    ).model_dump()
                )
            elif control.action == "clear_memory":
                logger.info("Conversation memory clear requested by client.")
                _clear_memory_event.set()
                await manager.broadcast(
                    StatusMessage(
                        status="memory_cleared",
                        detail="Conversation memory cleared",
                    ).model_dump()
                )
            else:
                await manager.send_personal(
                    websocket,
                    ErrorMessage(
                        error=f"Unknown action: {control.action}",
                        recoverable=True,
                    ).model_dump(),
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ── Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import sys
    import time

    max_retries = 5
    retry_delay = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            uvicorn.run(
                app,
                host="0.0.0.0",
                port=settings.WEBSOCKET_PORT,
                reload=False,
                log_level="info",
            )
            break
        except OSError as e:
            if e.errno == 10048 and attempt < max_retries:  # "Address already in use"
                logger.warning(
                    f"Port {settings.WEBSOCKET_PORT} in use (attempt {attempt}/{max_retries}). "
                    f"Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to bind to port {settings.WEBSOCKET_PORT}: {e}")
                sys.exit(1)

