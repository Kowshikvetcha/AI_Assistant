"""
Pydantic models for data exchange between components.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class MessageType(str, Enum):
    """WebSocket message types."""
    TRANSCRIPT = "transcript"
    LLM_RESPONSE = "llm_response"
    STATUS = "status"
    ERROR = "error"
    CONTROL = "control"


class TranscriptMessage(BaseModel):
    """Speech-to-text transcript result."""
    type: MessageType = MessageType.TRANSCRIPT
    text: str = Field(..., description="Transcribed text")
    timestamp: float = Field(..., description="Unix timestamp")
    latency_ms: float = Field(0.0, description="STT processing latency in ms")


class LLMResponse(BaseModel):
    """Structured LLM answer for interview questions."""
    type: MessageType = MessageType.LLM_RESPONSE
    summary: str = Field("", description="Brief summary of the answer")
    direct_answer: str = Field("", description="Direct, concise answer")
    bullet_points: list[str] = Field(
        default_factory=list, description="Key points as bullet list"
    )
    code_example: str = Field("", description="Code snippet if relevant")
    followup_question: str = Field(
        "", description="Suggested follow-up question"
    )
    latency_ms: float = Field(0.0, description="LLM processing latency in ms")
    tokens_used: int = Field(0, description="Total tokens consumed")


class StatusMessage(BaseModel):
    """Status update message."""
    type: MessageType = MessageType.STATUS
    status: str = Field(..., description="Status text")
    detail: str = Field("", description="Additional detail")


class ErrorMessage(BaseModel):
    """Error message."""
    type: MessageType = MessageType.ERROR
    error: str = Field(..., description="Error description")
    recoverable: bool = Field(True, description="Whether the error is recoverable")


class ControlMessage(BaseModel):
    """Control command from frontend."""
    type: MessageType = MessageType.CONTROL
    action: str = Field(..., description="Action: start, stop, clear")


class PerformanceMetrics(BaseModel):
    """Performance tracking for a single processing cycle."""
    stt_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    tokens_used: int = 0
    timestamp: float = 0.0


class ChatRequest(BaseModel):
    """Manual chat request from the UI."""
    question: str = Field(..., min_length=1, description="User question text")
