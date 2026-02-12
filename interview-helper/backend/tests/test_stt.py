"""
Unit tests for the STT (Speech-to-Text) service.
Mocks the OpenAI Whisper API to test transcription, retries, and rate limits.
"""

import io
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stt import transcribe_audio, _get_client


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the module-level client before each test."""
    import stt
    stt._client = None
    yield
    stt._client = None


def _make_wav_bytes() -> bytes:
    """Create minimal valid WAV bytes for testing."""
    import wave
    import numpy as np

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        data = (np.zeros(16000, dtype=np.int16)).tobytes()
        wf.writeframes(data)
    buf.seek(0)
    return buf.read()


@pytest.mark.asyncio
async def test_transcribe_success():
    """Test successful transcription returns text and latency."""
    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        return_value="Hello, this is a test transcript."
    )

    with patch("stt._get_client", return_value=mock_client):
        text, latency = await transcribe_audio(
            _make_wav_bytes(), api_key="test-key"
        )

    assert text == "Hello, this is a test transcript."
    assert latency > 0
    mock_client.audio.transcriptions.create.assert_called_once()


@pytest.mark.asyncio
async def test_transcribe_empty_response():
    """Test that empty transcription returns empty string."""
    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value="  ")

    with patch("stt._get_client", return_value=mock_client):
        text, latency = await transcribe_audio(
            _make_wav_bytes(), api_key="test-key"
        )

    assert text == ""
    assert latency > 0


@pytest.mark.asyncio
async def test_transcribe_retry_on_api_error():
    """Test that API errors trigger retries."""
    from openai import APIError

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.headers = {}

    # Fail twice, succeed on third
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=[
            APIError(
                message="Server error",
                request=None,
                body=None,
            ),
            APIError(
                message="Server error",
                request=None,
                body=None,
            ),
            "Recovered transcript",
        ]
    )

    with patch("stt._get_client", return_value=mock_client):
        text, latency = await transcribe_audio(
            _make_wav_bytes(), api_key="test-key", max_retries=3
        )

    assert text == "Recovered transcript"
    assert mock_client.audio.transcriptions.create.call_count == 3


@pytest.mark.asyncio
async def test_transcribe_all_retries_exhausted():
    """Test that RuntimeError is raised when all retries fail."""
    from openai import APIError

    mock_client = AsyncMock()

    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=APIError(
            message="Persistent error",
            request=None,
            body=None,
        )
    )

    with patch("stt._get_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="STT failed"):
            await transcribe_audio(
                _make_wav_bytes(), api_key="test-key", max_retries=2
            )

    assert mock_client.audio.transcriptions.create.call_count == 2


@pytest.mark.asyncio
async def test_transcribe_rate_limit_backoff():
    """Test rate limit handling with exponential backoff."""
    from openai import RateLimitError

    mock_client = AsyncMock()

    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=[
            RateLimitError(
                message="Rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            ),
            "After rate limit",
        ]
    )

    with patch("stt._get_client", return_value=mock_client):
        with patch("stt.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, _ = await transcribe_audio(
                _make_wav_bytes(), api_key="test-key", max_retries=3
            )

    assert text == "After rate limit"
    # Should have slept with exponential backoff (2^1 = 2)
    mock_sleep.assert_called_once_with(2)
