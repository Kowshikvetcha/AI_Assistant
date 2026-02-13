"""
FastAPI application — main entry point for the interview helper backend.

Orchestrates: audio capture → STT → LLM → WebSocket broadcast.
"""

import asyncio
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from models import (
    MessageType,
    StatusMessage,
    ErrorMessage,
    PerformanceMetrics,
    TranscriptMessage,
)
from websocket_manager import ConnectionManager, parse_control_message
from audio_capture import capture_system_audio
from stt import transcribe_audio
from llm import generate_answer, summarize_context
from resume_parser import parse_resume
from utils import setup_logging, encode_wav, is_silent, perf_timer

# ── Globals ──────────────────────────────────────────────────────────
settings = get_settings()
logger = setup_logging(settings.LOG_LEVEL)
manager = ConnectionManager()

# Pipeline state
_capture_task: asyncio.Task | None = None
_is_capturing = False
_resume_context: str = ""
_resume_filename: str = ""


# ── Lifespan ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("🚀 Interview Helper backend starting...")
    logger.info(f"   Port:  {settings.WEBSOCKET_PORT}")
    logger.info(f"   Model: {settings.LLM_MODEL}")
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

    except Exception as e:
        logger.warning(f"Audio producer stopped: {e}")


async def _audio_consumer():
    """Process audio chunks from the queue: STT → broadcast → debounced LLM."""
    transcript_buffer: list[str] = []
    interview_summary: str = ""
    chunks_since_llm = 0
    _llm_task: asyncio.Task | None = None

    while _is_capturing:
        try:
            # Wait for next audio chunk (with timeout to check _is_capturing)
            try:
                wav_bytes = await asyncio.wait_for(_audio_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                # Timeout = speech pause → trigger LLM if we have new transcripts
                if chunks_since_llm > 0 and transcript_buffer:
                    combined_text = " ".join(transcript_buffer)
                    # Cancel previous LLM if still running
                    if _llm_task and not _llm_task.done():
                        _llm_task.cancel()
                    _llm_task = asyncio.create_task(
                        _process_llm(combined_text, 0, interview_summary, _resume_context)
                    )
                    chunks_since_llm = 0
                    logger.info("🧠 LLM triggered (speech pause)")
                continue

            # ── STT ──────────────────────────────────────────────
            try:
                transcript, stt_latency = await transcribe_audio(
                    wav_bytes, settings.OPENAI_API_KEY
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
            transcript_buffer.append(transcript)
            chunks_since_llm += 1

            # ── Two-Tier Memory Management ──────────────────────
            # If buffer gets too large (>10 chunks / ~20s), compress oldest chunks
            if len(transcript_buffer) >= 10:
                # Take oldest 5 chunks to summarize
                to_summarize = " ".join(transcript_buffer[:5])
                # Keep newest chunks in buffer
                transcript_buffer = transcript_buffer[5:]
                
                # Update summary (async, may block consumer briefly but queue handles it)
                interview_summary = await summarize_context(
                    old_summary=interview_summary,
                    new_text=to_summarize,
                    api_key=settings.OPENAI_API_KEY,
                )

            # Call LLM after 2 chunks (~4s of speech) — balances
            # freshness vs stability of the answer panel
            if chunks_since_llm >= 2:
                combined_text = " ".join(transcript_buffer)
                # Cancel previous LLM if still running
                if _llm_task and not _llm_task.done():
                    _llm_task.cancel()
                _llm_task = asyncio.create_task(
                    _process_llm(combined_text, stt_latency, interview_summary, _resume_context)
                )
                chunks_since_llm = 0
                logger.info("🧠 LLM triggered (enough context)")

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
            api_key=settings.OPENAI_API_KEY,
            model=settings.LLM_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            interview_summary=interview_summary,
            resume_context=resume_context,
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

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.WEBSOCKET_PORT,
        reload=False,
        log_level="info",
    )
