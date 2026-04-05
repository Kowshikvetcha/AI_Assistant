"""Focused tests for HTTP routes that orchestrate answer modes."""

from unittest.mock import AsyncMock, patch

import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from models import InputMode, LLMResponse


client = TestClient(app)


def _sample_response(mode: InputMode) -> LLMResponse:
    return LLMResponse(
        input_mode=mode,
        corrected_question="Which option is correct?",
        summary="Picks the right option",
        direct_answer="Answer: B. Correct option.",
        bullet_points=["Reason 1", "Reason 2"],
        code_example="",
        followup_question="Why not A?",
        latest_question_input="Which option is correct?",
        latency_ms=10,
        tokens_used=42,
    )


def test_chat_route_uses_text_mode():
    with patch("main.generate_answer", new=AsyncMock(return_value=(_sample_response(InputMode.TEXT), 10, 42))) as mock_generate:
        response = client.post("/chat", json={"question": "Explain REST"})

    assert response.status_code == 200
    assert response.json()["input_mode"] == "text"
    assert mock_generate.await_args.kwargs["input_mode"] == InputMode.TEXT


def test_answer_screen_route_uses_screen_mode():
    with patch("main.extract_text_from_image", return_value="What is 2+2? A.3 B.4 C.5"):
        with patch("main.generate_answer", new=AsyncMock(return_value=(_sample_response(InputMode.SCREEN), 10, 42))) as mock_generate:
            response = client.post("/answer-screen", json={"image": "dGVzdA=="})

    assert response.status_code == 200
    body = response.json()
    assert body["input_mode"] == "screen"
    assert body["ocr_text"] == "What is 2+2? A.3 B.4 C.5"
    assert mock_generate.await_args.kwargs["input_mode"] == InputMode.SCREEN
