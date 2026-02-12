"""
Configuration management using Pydantic Settings.
Loads values from .env file in the project root.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

# Resolve .env path relative to this file's parent (backend/) -> project root
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # OpenAI
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key")
    LLM_MODEL: str = Field("gpt-4o", description="OpenAI model for LLM")
    LLM_MAX_TOKENS: int = Field(1024, description="Max tokens for LLM response")

    # Server
    WEBSOCKET_PORT: int = Field(8765, description="WebSocket server port")

    # Audio
    AUDIO_CHUNK_DURATION: float = Field(
        2.0, description="Audio chunk duration in seconds"
    )

    # Logging
    LOG_LEVEL: str = Field("INFO", description="Logging level")

    model_config = {
        "env_file": str(ENV_PATH),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
