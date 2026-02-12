"""
Speech-to-Text service using OpenAI Whisper API.
Handles async transcription with retry logic and rate limit handling.
"""

import asyncio
import io
import logging
import time
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from utils import perf_timer, encode_wav

logger = logging.getLogger("interview_helper")

# Module-level client — initialized lazily
_client: AsyncOpenAI | None = None


def _get_client(api_key: str) -> AsyncOpenAI:
    """Get or create the async OpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=api_key, timeout=30.0)
    return _client


async def transcribe_audio(
    audio_data: bytes,
    api_key: str,
    max_retries: int = 3,
    language: str = "en",
) -> tuple[str, float]:
    """Transcribe audio bytes using OpenAI Whisper API.

    Args:
        audio_data: WAV-encoded audio bytes.
        api_key: OpenAI API key.
        max_retries: Number of retry attempts on failure.
        language: Language hint for transcription.

    Returns:
        Tuple of (transcript_text, latency_ms).

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    client = _get_client(api_key)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            with perf_timer("whisper_api", logger) as t:
                # Wrap bytes in a file-like object with a .wav name
                audio_file = io.BytesIO(audio_data)
                audio_file.name = "audio.wav"

                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="text",
                )

            transcript = response.strip() if isinstance(response, str) else response.text.strip()
            latency = t["elapsed_ms"]

            if transcript:
                logger.info(
                    f"📝 Transcript ({latency:.0f}ms): "
                    f"{transcript[:80]}{'...' if len(transcript) > 80 else ''}"
                )
            else:
                logger.debug(f"📝 Empty transcript ({latency:.0f}ms)")

            return transcript, latency

        except RateLimitError as e:
            wait_time = min(2 ** attempt, 10)
            logger.warning(
                f"⚠️  Rate limited (attempt {attempt}/{max_retries}), "
                f"waiting {wait_time}s..."
            )
            last_error = e
            await asyncio.sleep(wait_time)

        except APITimeoutError as e:
            logger.warning(
                f"⚠️  Whisper API timeout (attempt {attempt}/{max_retries})"
            )
            last_error = e
            await asyncio.sleep(1)

        except APIError as e:
            logger.error(
                f"❌ Whisper API error (attempt {attempt}/{max_retries}): {e}"
            )
            last_error = e
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"❌ Unexpected STT error: {e}")
            last_error = e
            break

    raise RuntimeError(
        f"STT failed after {max_retries} attempts: {last_error}"
    )
