"""
LLM answer generator using OpenAI GPT-4o.
Produces structured interview answers from transcripts.
"""

import asyncio
import json
import logging
import re
from typing import Optional
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from config import get_settings
from models import LLMResponse
from utils import perf_timer

logger = logging.getLogger("interview_helper")
settings = get_settings()

SYSTEM_PROMPT = """You are a technical interview copilot. Your job is to produce accurate, concise, interview-ready answers.

IMPORTANT — Speech-to-text input:
The questions you receive are transcribed from live audio using speech-to-text. The transcription is often imperfect — expect misspellings, phonetic errors, missing or swapped words, and garbled technical terms. You MUST:
- Infer the actual intended question from the noisy transcription before answering.
- If a word does not make sense literally, consider what it sounds like spoken aloud and pick the most plausible technical term.
- Use the surrounding context (interview topic, other words in the sentence) to disambiguate.
- Silently correct obvious STT errors — do NOT point them out or comment on transcription quality.

Common STT misheard technical terms (not exhaustive — apply this reasoning broadly):
  "cash" / "kash" → cache, "sequel" → SQL, "pie torch" / "pie tors" → PyTorch,
  "tensor flow" → TensorFlow, "kuber netties" / "kuber net ease" → Kubernetes,
  "post gress" / "post gray" → PostgreSQL, "no JS" / "know JS" → Node.js,
  "react native" vs "react natively", "mongo db" → MongoDB, "redis" / "red is" → Redis,
  "doc er" / "docker" → Docker, "get hub" → GitHub, "J query" → jQuery,
  "next JS" / "next yes" → Next.js, "type script" → TypeScript, "my sequel" → MySQL,
  "sass" → SaaS or Sass (use context), "lambda" / "lam da" → Lambda,
  "dynamo db" / "dynamo" → DynamoDB, "es six" / "ES six" → ES6,
  "GPT for" / "GPT for all" → GPT-4, "LLM" / "elm" → LLM,
  "RAG" / "rag" → RAG (Retrieval-Augmented Generation),
  "fine tune" / "fine-tune", "embedding" / "in bedding" → embedding,
  "transformer" / "trans former", "API" / "a pie" → API.

You MUST output valid JSON with exactly this schema:
{
  "corrected_question": "The question as you understood it, with STT errors corrected",
  "summary": "One-line summary of the question",
  "direct_answer": "Clear spoken answer (2-4 sentences)",
  "bullet_points": ["Key point 1", "Key point 2", "Key point 3"],
  "code_example": "Short code snippet if relevant, otherwise empty string",
  "followup_question": "One strong interviewer-style follow-up question"
}

Behavior rules:
- First, reconstruct the intended question in corrected_question. Then answer THAT corrected version.
- Primary objective: answer the latest question first and in the most detail.
- Treat any older interview context as low-priority background only.
- If older context conflicts with the latest question, prioritize the latest question.
- If multiple questions appear, answer only the most recent question unless the user explicitly asks to combine them.
- Be correct first, concise second.
- Prefer practical tradeoffs, not generic theory.
- If context is ambiguous, state the most likely interpretation in direct_answer.
- Do not invent resume/project details. Use candidate background only when explicitly relevant.
- If unsure, say so briefly and provide the safest technically correct answer.
- Keep bullet_points to 3-5 short items.
- code_example must be empty unless the question is coding/implementation focused.
- If the latest question is coding/implementation relevant, code_example is required.
- For coding questions, provide a short, correct, runnable snippet (8-25 lines), not pseudocode.
- Prefer the language implied by the question; if unclear, default to Python.
- Keep code focused on the main idea and avoid unnecessary boilerplate.
- Never include markdown fences, commentary, or any text outside the JSON object.

Tone and delivery rules (important):
- direct_answer must sound like natural spoken interview speech, not a written essay.
- Use first-person when appropriate (for example: "I’d approach this by...").
- Keep direct_answer to 3-5 short sentences that can be read aloud in one breath.
- Start with a clear one-line answer, then add practical reasoning.
- Prefer plain words over jargon unless jargon is necessary for accuracy.
- Avoid robotic transitions like "Certainly", "In conclusion", "Overall", or "As an AI".
- Do not use buzzword-heavy or generic filler phrasing.
- If useful, include one concrete real-world example in one sentence.
- Keep confidence calibrated: confident when certain, explicit uncertainty when not.

Question-type handling:
- First classify the latest question as one of: conceptual/theory, coding/implementation, system design/architecture, behavioral.
- Adapt depth and tone to that question type.

Conceptual/theory answer format:
- direct_answer should be 4-6 short sentences.
- Use this order:
  1) One-sentence definition.
  2) One-sentence intuition (simple mental model or analogy if useful).
  3) One-sentence practical impact in real engineering/ML work.
  4) One-sentence concrete levers to tune/improve outcomes.
  5) Optional one-sentence example.
- Avoid generic textbook phrasing; include at least one concrete lever/decision variable when relevant.
- For conceptual/theory questions, code_example must be empty.

Coding/implementation answer format:
- direct_answer can be shorter (3-5 short sentences) and should focus on approach + tradeoffs.
- code_example is required and should be practical, correct, and minimal.
"""

SUMMARY_PROMPT = """Compress the following interview transcript into a brief summary (3-5 sentences max).
Capture: key topics discussed, questions asked, and important answers given.
Do NOT include filler or repetition. Output ONLY the summary text, no JSON."""

JSON_REPAIR_PROMPT = """You repair malformed model output into valid JSON.

Return ONLY a valid JSON object with exactly these keys:
- corrected_question (string)
- summary (string)
- direct_answer (string)
- bullet_points (array of strings)
- code_example (string)
- followup_question (string)

Rules:
- Preserve original meaning as much as possible.
- If any field is missing, set it to an empty value.
- Do not add extra keys.
- No markdown, no explanations, JSON only.
"""

# Module-level client
_client: AsyncOpenAI | None = None
_client_config: tuple[str, Optional[str]] | None = None


def _get_client(api_key: str, base_url: Optional[str] = None) -> AsyncOpenAI:
    """Get or create the async OpenAI client."""
    global _client, _client_config
    cfg = (api_key, base_url)
    if _client is None or _client_config != cfg:
        kwargs = {"api_key": api_key, "timeout": 30.0}
        if base_url:
            kwargs["base_url"] = base_url
        _client = AsyncOpenAI(**kwargs)
        _client_config = cfg
    return _client


def _parse_llm_json(raw: str) -> dict | None:
    """Parse LLM response text into a dict. Returns None if invalid."""
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _fallback_payload_from_text(raw: str) -> dict:
    """Final fallback payload when parsing/repair both fail."""
    text = raw.strip()
    return {
        "corrected_question": "",
        "summary": "",
        "direct_answer": text[:500],
        "bullet_points": [],
        "code_example": "",
        "followup_question": "",
    }


def _normalize_payload(payload: dict) -> dict:
    """Normalize payload to expected schema and types."""
    bullets = payload.get("bullet_points", [])
    if not isinstance(bullets, list):
        bullets = [str(bullets)]
    bullets = [str(b).strip() for b in bullets if str(b).strip()]

    return {
        "corrected_question": str(payload.get("corrected_question", "")).strip(),
        "summary": str(payload.get("summary", "")).strip(),
        "direct_answer": str(payload.get("direct_answer", "")).strip(),
        "bullet_points": bullets,
        "code_example": str(payload.get("code_example", "")).strip(),
        "followup_question": str(payload.get("followup_question", "")).strip(),
    }


def _split_latest_question(transcript: str) -> tuple[str, str]:
    """Return (latest_question, supporting_context) from recent transcript text."""
    text = transcript.strip()
    if not text:
        return "", ""

    # Prefer the last sentence that ends with a question mark.
    q_matches = list(re.finditer(r"[^?]*\?", text, flags=re.DOTALL))
    if q_matches:
        latest_q = q_matches[-1].group(0).strip()
        prefix = text[:q_matches[-1].start()].strip()
        suffix = text[q_matches[-1].end():].strip()
        support_parts = [part for part in (prefix, suffix) if part]
        return latest_q, "\n".join(support_parts)

    # If no explicit question mark is present, prefer the full recent utterance.
    # This avoids sending trailing fragments like "of recommendation systems."
    normalized = " ".join(part.strip() for part in text.splitlines() if part.strip())
    return normalized, ""


async def _repair_llm_json(
    raw_content: str,
    client: AsyncOpenAI,
    model: str,
) -> dict | None:
    """Attempt one strict JSON repair pass using the same LLM."""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JSON_REPAIR_PROMPT},
                {"role": "user", "content": raw_content},
            ],
            max_tokens=500,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        repaired_raw = response.choices[0].message.content or ""
        repaired = _parse_llm_json(repaired_raw)
        if repaired is None:
            return None
        return _normalize_payload(repaired)
    except Exception as e:
        logger.warning(f"JSON repair pass failed: {e}")
        return None


async def generate_answer(
    transcript: str,
    api_key: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    max_retries: int = 3,
    interview_summary: str = "",
    resume_context: str = "",
    base_url: Optional[str] = None,
) -> tuple[LLMResponse, float, int]:
    """Generate a structured interview answer from a transcript.

    Args:
        transcript: Recent transcribed speech.
        api_key: OpenAI API key.
        model: Model name (e.g. gpt-4o, gpt-4-turbo).
        max_tokens: Maximum tokens in the response.
        resume_context: Extracted text from the user's resume.
        max_retries: Retry attempts on failure.
        interview_summary: Running summary of earlier conversation.

    Returns:
        Tuple of (LLMResponse, latency_ms, tokens_used).

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    client = _get_client(api_key, base_url=base_url)
    effective_model = model or settings.llm_model
    last_error: Exception | None = None

    latest_question, supporting_context = _split_latest_question(transcript)
    if not latest_question:
        latest_question = transcript.strip()

    # Build context-aware user message with explicit priority ordering.
    user_content = ""
    if resume_context:
        user_content += f"[Candidate background - low priority]\n{resume_context}\n\n"
    if interview_summary:
        user_content += f"[Older interview summary - low priority]\n{interview_summary}\n\n"
    if supporting_context:
        user_content += f"[Recent supporting context - medium priority]\n{supporting_context}\n\n"
    user_content += f"[Latest question - highest priority - transcribed from speech, may contain errors]\n{latest_question}"

    for attempt in range(1, max_retries + 1):
        try:
            with perf_timer("llm_api", logger) as t:
                response = await client.chat.completions.create(
                    model=effective_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )

            latency = t["elapsed_ms"]
            raw_content = response.choices[0].message.content or ""
            tokens_used = response.usage.total_tokens if response.usage else 0

            parsed = _parse_llm_json(raw_content)
            if parsed is None:
                logger.warning("Primary JSON parse failed, running repair pass")
                parsed = await _repair_llm_json(raw_content, client, effective_model)
            if parsed is None:
                logger.warning("JSON repair failed, using text fallback payload")
                parsed = _fallback_payload_from_text(raw_content)
            parsed = _normalize_payload(parsed)
            llm_response = LLMResponse(
                corrected_question=parsed.get("corrected_question", ""),
                summary=parsed.get("summary", ""),
                direct_answer=parsed.get("direct_answer", ""),
                bullet_points=parsed.get("bullet_points", []),
                code_example=parsed.get("code_example", ""),
                followup_question=parsed.get("followup_question", ""),
                latest_question_input=latest_question,
                latency_ms=latency,
                tokens_used=tokens_used,
            )

            logger.info(
                f"🤖 LLM response ({latency:.0f}ms, {tokens_used} tokens): "
                f"{llm_response.summary[:60]}..."
            )

            return llm_response, latency, tokens_used

        except RateLimitError as e:
            wait_time = min(2 ** attempt, 10)
            logger.warning(
                f"⚠️  LLM rate limited (attempt {attempt}/{max_retries}), "
                f"waiting {wait_time}s..."
            )
            last_error = e
            await asyncio.sleep(wait_time)

        except APITimeoutError as e:
            logger.warning(
                f"⚠️  LLM timeout (attempt {attempt}/{max_retries})"
            )
            last_error = e
            await asyncio.sleep(1)

        except APIError as e:
            logger.error(
                f"❌ LLM API error (attempt {attempt}/{max_retries}): {e}"
            )
            last_error = e
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"❌ Unexpected LLM error: {e}")
            last_error = e
            break

    raise RuntimeError(
        f"LLM failed after {max_retries} attempts. "
        f"Last error: {last_error}. "
        "Check your AI_API_KEY, AI_BASE_URL, and LLM_MODEL settings in the .env file."
    )


async def summarize_context(
    old_summary: str,
    new_text: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """Compress old transcript text into a running summary.

    Uses GPT-4o-mini for speed and cost efficiency.

    Args:
        old_summary: Existing interview summary (may be empty).
        new_text: New transcript text to fold into the summary.
        api_key: OpenAI API key.

    Returns:
        Updated summary string.
    """
    client = _get_client(api_key, base_url=base_url)
    effective_model = model or settings.summary_model

    content = ""
    if old_summary:
        content += f"Previous summary:\n{old_summary}\n\n"
    content += f"New transcript to incorporate:\n{new_text}"

    try:
        with perf_timer("summary_api", logger) as t:
            response = await client.chat.completions.create(
                model=effective_model,
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": content},
                ],
                max_tokens=300,
                temperature=0.2,
            )

        summary = response.choices[0].message.content or ""
        logger.info(f"📋 Summary updated ({t['elapsed_ms']:.0f}ms): {summary[:60]}...")
        return summary.strip()

    except Exception as e:
        logger.error(f"❌ Summary generation failed: {e}")
        # Fall back to keeping old summary
        return old_summary
