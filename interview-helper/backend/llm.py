"""
LLM answer generator using OpenAI GPT-4o.
Produces structured interview answers from transcripts.
"""

import asyncio
import json
import logging
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from models import LLMResponse
from utils import perf_timer

logger = logging.getLogger("interview_helper")

SYSTEM_PROMPT = """You are an expert technical interview assistant. Provide concise, structured, high-quality answers suitable for live interviews. Avoid unnecessary verbosity. Provide bullet points and short explanations.

You MUST respond in valid JSON with this exact schema:
{
  "summary": "One-line summary of what was asked",
  "direct_answer": "Clear, direct answer (2-3 sentences max)",
  "bullet_points": ["Key point 1", "Key point 2", "Key point 3"],
  "code_example": "Short code snippet if relevant, otherwise empty string",
  "followup_question": "A smart follow-up question they might ask"
}

Rules:
- Keep answers concise and interview-appropriate
- Use bullet_points for structured key takeaways
- Only include code_example if the question is about coding
- If the candidate's resume/background is provided, tailor answers to highlight their relevant experience, skills, and projects
- Respond ONLY with JSON, no markdown fences or extra text"""

SUMMARY_PROMPT = """Compress the following interview transcript into a brief summary (3-5 sentences max).
Capture: key topics discussed, questions asked, and important answers given.
Do NOT include filler or repetition. Output ONLY the summary text, no JSON."""

# Module-level client
_client: AsyncOpenAI | None = None


def _get_client(api_key: str) -> AsyncOpenAI:
    """Get or create the async OpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=api_key, timeout=30.0)
    return _client


def _parse_llm_json(raw: str) -> dict:
    """Parse LLM response text into a dict, handling common issues."""
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
        logger.warning(f"Failed to parse LLM JSON, returning raw text")
        return {
            "summary": "",
            "direct_answer": text[:500],
            "bullet_points": [],
            "code_example": "",
            "followup_question": "",
        }


async def generate_answer(
    transcript: str,
    api_key: str,
    model: str = "gpt-4o",
    max_tokens: int = 1024,
    max_retries: int = 3,
    interview_summary: str = "",
    resume_context: str = "",
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
    client = _get_client(api_key)
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
    client = _get_client(api_key)

    content = ""
    if old_summary:
        content += f"Previous summary:\n{old_summary}\n\n"
    content += f"New transcript to incorporate:\n{new_text}"

    try:
        with perf_timer("summary_api", logger) as t:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
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
