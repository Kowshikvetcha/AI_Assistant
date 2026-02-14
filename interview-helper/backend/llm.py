"""
LLM answer generator using OpenAI GPT-4o.
Produces structured interview answers from transcripts.
"""

import asyncio
import json
import logging
from typing import Optional
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from models import LLMResponse
from utils import perf_timer

logger = logging.getLogger("interview_helper")

SYSTEM_PROMPT = """You are a technical interview copilot. Your job is to produce accurate, concise, interview-ready answers.

You MUST output valid JSON with exactly this schema:
{
  "summary": "One-line summary of the question",
  "direct_answer": "Clear spoken answer (2-4 sentences)",
  "bullet_points": ["Key point 1", "Key point 2", "Key point 3"],
  "code_example": "Short code snippet if relevant, otherwise empty string",
  "followup_question": "One strong interviewer-style follow-up question"
}

Behavior rules:
- Be correct first, concise second.
- Prefer practical tradeoffs, not generic theory.
- If context is ambiguous, state the most likely interpretation in direct_answer.
- Do not invent resume/project details. Use candidate background only when explicitly relevant.
- If unsure, say so briefly and provide the safest technically correct answer.
- Keep bullet_points to 3-5 short items.
- code_example must be empty unless the question is coding/implementation focused.
- Never include markdown fences, commentary, or any text outside the JSON object.
"""

SUMMARY_PROMPT = """Compress the following interview transcript into a brief summary (3-5 sentences max).
Capture: key topics discussed, questions asked, and important answers given.
Do NOT include filler or repetition. Output ONLY the summary text, no JSON."""

JSON_REPAIR_PROMPT = """You repair malformed model output into valid JSON.

Return ONLY a valid JSON object with exactly these keys:
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
        "summary": str(payload.get("summary", "")).strip(),
        "direct_answer": str(payload.get("direct_answer", "")).strip(),
        "bullet_points": bullets,
        "code_example": str(payload.get("code_example", "")).strip(),
        "followup_question": str(payload.get("followup_question", "")).strip(),
    }


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
    model: str = "gpt-4o",
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
    last_error: Exception | None = None

    # Build context-aware user message
    user_content = ""
    if resume_context:
        user_content += f"[Candidate background]\n{resume_context}\n\n"
    if interview_summary:
        user_content += f"[Interview so far]\n{interview_summary}\n\n"
    user_content += f"[Recent speech]\n{transcript}"

    for attempt in range(1, max_retries + 1):
        try:
            with perf_timer("llm_api", logger) as t:
                response = await client.chat.completions.create(
                    model=model,
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
                parsed = await _repair_llm_json(raw_content, client, model)
            if parsed is None:
                logger.warning("JSON repair failed, using text fallback payload")
                parsed = _fallback_payload_from_text(raw_content)
            parsed = _normalize_payload(parsed)
            llm_response = LLMResponse(
                summary=parsed.get("summary", ""),
                direct_answer=parsed.get("direct_answer", ""),
                bullet_points=parsed.get("bullet_points", []),
                code_example=parsed.get("code_example", ""),
                followup_question=parsed.get("followup_question", ""),
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
        f"LLM failed after {max_retries} attempts: {last_error}"
    )


async def summarize_context(
    old_summary: str,
    new_text: str,
    api_key: str,
    model: str = "gpt-4o-mini",
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

    content = ""
    if old_summary:
        content += f"Previous summary:\n{old_summary}\n\n"
    content += f"New transcript to incorporate:\n{new_text}"

    try:
        with perf_timer("summary_api", logger) as t:
            response = await client.chat.completions.create(
                model=model,
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
