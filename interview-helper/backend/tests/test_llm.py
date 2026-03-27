"""
Unit tests for the LLM answer generator.
Mocks the OpenAI GPT-4o API to test JSON parsing, error handling, and token logging.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm import generate_answer, _parse_llm_json
from models import LLMResponse


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the module-level client before each test."""
    import llm
    llm._client = None
    yield
    llm._client = None


VALID_LLM_JSON = json.dumps({
    "corrected_question": "What is a Python decorator?",
    "summary": "Explains Python decorators",
    "direct_answer": "A decorator is a function that takes another function and extends its behavior.",
    "bullet_points": [
        "Use @syntax for decoration",
        "Decorators wrap functions",
        "Common for logging, auth, caching",
    ],
    "code_example": "@my_decorator\ndef my_func():\n    pass",
    "followup_question": "Can you explain functools.wraps?",
})


def _mock_completion(content: str, tokens: int = 150):
    """Build a mock OpenAI chat completion response."""
    mock_usage = MagicMock()
    mock_usage.total_tokens = tokens

    mock_message = MagicMock()
    mock_message.content = content

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    return mock_response


@pytest.mark.asyncio
async def test_generate_answer_success():
    """Test successful LLM response parsing."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion(VALID_LLM_JSON, tokens=200)
    )

    with patch("llm._get_client", return_value=mock_client):
        resp, latency, tokens = await generate_answer(
            "What is a Python decorator?", api_key="test-key"
        )

    assert isinstance(resp, LLMResponse)
    assert resp.summary == "Explains Python decorators"
    assert len(resp.bullet_points) == 3
    assert "decorator" in resp.code_example.lower() or "@" in resp.code_example
    assert tokens == 200
    assert latency > 0


@pytest.mark.asyncio
async def test_generate_answer_with_markdown_fences():
    """Test JSON extraction when LLM wraps response in markdown code fences."""
    fenced = f"```json\n{VALID_LLM_JSON}\n```"
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion(fenced)
    )

    with patch("llm._get_client", return_value=mock_client):
        resp, _, _ = await generate_answer(
            "What is a decorator?", api_key="test-key"
        )

    assert resp.summary == "Explains Python decorators"


@pytest.mark.asyncio
async def test_generate_answer_invalid_json():
    """Test graceful handling of non-JSON LLM output."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("This is just plain text, not JSON")
    )

    with patch("llm._get_client", return_value=mock_client):
        resp, _, _ = await generate_answer(
            "Tell me something", api_key="test-key"
        )

    # Should fall back — direct_answer gets the raw text
    assert "plain text" in resp.direct_answer
    assert resp.summary == ""


@pytest.mark.asyncio
async def test_generate_answer_retry_on_error():
    """Test retry behavior on API errors."""
    from openai import APIError

    mock_client = AsyncMock()

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            APIError(message="Error", request=None, body=None),
            _mock_completion(VALID_LLM_JSON),
        ]
    )

    with patch("llm._get_client", return_value=mock_client):
        resp, _, _ = await generate_answer(
            "Retry test", api_key="test-key", max_retries=3
        )

    assert resp.summary == "Explains Python decorators"
    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_generate_answer_all_retries_fail():
    """Test RuntimeError when all retries are exhausted."""
    from openai import APIError

    mock_client = AsyncMock()

    mock_client.chat.completions.create = AsyncMock(
        side_effect=APIError(message="Error", request=None, body=None)
    )

    with patch("llm._get_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="LLM failed"):
            await generate_answer(
                "Fail test", api_key="test-key", max_retries=2
            )


def test_parse_llm_json_valid():
    """Test direct JSON parsing."""
    result = _parse_llm_json(VALID_LLM_JSON)
    assert result["summary"] == "Explains Python decorators"


def test_parse_llm_json_with_fences():
    """Test parsing JSON with markdown fences."""
    fenced = f"```json\n{VALID_LLM_JSON}\n```"
    result = _parse_llm_json(fenced)
    assert result["summary"] == "Explains Python decorators"


def test_parse_llm_json_invalid():
    """Test that invalid JSON returns None (caller handles fallback)."""
    result = _parse_llm_json("not valid json at all")
    assert result is None
