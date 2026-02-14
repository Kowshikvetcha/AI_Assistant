"""
Configuration management using Pydantic Settings.
Loads values from .env file in the project root.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field

# Resolve .env path relative to this file's parent (backend/) -> project root
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


# OpenAI-compatible provider presets.
# Users can always override URL/models explicitly in .env.
PROVIDER_PRESETS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-4o",
        "summary_model": "gpt-4o-mini",
        "stt_model": "whisper-1",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "llm_model": "openai/gpt-4o-mini",
        "summary_model": "openai/gpt-4o-mini",
        "stt_model": "whisper-1",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "llm_model": "llama-3.1-8b-instant",
        "summary_model": "llama-3.1-8b-instant",
        "stt_model": "whisper-large-v3",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "llm_model": "meta-llama/Llama-3.1-8B-Instruct-Turbo",
        "summary_model": "meta-llama/Llama-3.1-8B-Instruct-Turbo",
        "stt_model": "whisper-1",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "llm_model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "summary_model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "stt_model": "whisper-v3",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "llm_model": "deepseek-chat",
        "summary_model": "deepseek-chat",
        "stt_model": "whisper-1",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "llm_model": "llama3.1:8b",
        "summary_model": "llama3.1:8b",
        "stt_model": "whisper-1",
    },
}


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # AI provider + credentials
    AI_PROVIDER: str = Field("openai", description="AI provider name")
    AI_API_KEY: Optional[str] = Field(
        None,
        description="Provider API key (preferred generic field)",
    )
    OPENAI_API_KEY: Optional[str] = Field(
        None,
        description="Legacy OpenAI API key (backward compatibility)",
    )
    AI_BASE_URL: Optional[str] = Field(
        None,
        description="Optional provider base URL for OpenAI-compatible APIs",
    )

    # AI models
    LLM_MODEL: Optional[str] = Field(
        None, description="Primary LLM model (provider default if empty)"
    )
    SUMMARY_MODEL: Optional[str] = Field(
        None, description="Context summary model (provider default if empty)"
    )
    STT_MODEL: Optional[str] = Field(
        None, description="Speech-to-text model (provider default if empty)"
    )
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

    @property
    def api_key(self) -> str:
        """Return effective API key while keeping backward compatibility."""
        key = self.AI_API_KEY or self.OPENAI_API_KEY
        if not key:
            raise ValueError("Missing API key. Set AI_API_KEY (or OPENAI_API_KEY).")
        return key

    @property
    def provider(self) -> str:
        """Normalized provider key."""
        return (self.AI_PROVIDER or "openai").strip().lower()

    @property
    def base_url(self) -> Optional[str]:
        """Effective base URL: explicit .env value or provider preset."""
        if self.AI_BASE_URL:
            return self.AI_BASE_URL
        preset = PROVIDER_PRESETS.get(self.provider)
        if preset:
            return preset["base_url"]
        raise ValueError(
            f"Unknown AI_PROVIDER '{self.provider}'. Set AI_BASE_URL explicitly "
            "or use a supported provider preset."
        )

    def _resolve_model(self, explicit: Optional[str], preset_key: str, label: str) -> str:
        """Resolve model from explicit env value or provider preset."""
        if explicit:
            return explicit
        preset = PROVIDER_PRESETS.get(self.provider)
        if preset and preset_key in preset:
            return preset[preset_key]
        raise ValueError(
            f"Missing {label} for provider '{self.provider}'. Set {label} in .env."
        )

    @property
    def llm_model(self) -> str:
        """Effective main LLM model."""
        return self._resolve_model(self.LLM_MODEL, "llm_model", "LLM_MODEL")

    @property
    def summary_model(self) -> str:
        """Effective summary model."""
        return self._resolve_model(
            self.SUMMARY_MODEL, "summary_model", "SUMMARY_MODEL"
        )

    @property
    def stt_model(self) -> str:
        """Effective STT model."""
        return self._resolve_model(self.STT_MODEL, "stt_model", "STT_MODEL")


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
