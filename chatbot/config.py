"""Application configuration, read once from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VALID_AI_MODES = ("auto", "gemini", "ollama", "simulated")


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, "")))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _clean_key(value: str | None) -> str | None:
    """Trim spaces and stray quotes that are easy to paste by accident."""
    cleaned = (value or "").strip().strip("\"'").strip()
    return cleaned or None


@dataclass(frozen=True)
class Config:
    """All tunable settings. Defaults are safe for tests (no network, no download)."""

    # AI engines
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ai_mode: str = "auto"  # auto | gemini | ollama | simulated
    request_timeout: int = 30

    # Speech
    speech_lang: str = "en-GB"  # browser speech recognition + read-aloud language
    vosk_model_name: str = "vosk-model-small-en-us-0.15"
    models_dir: Path | None = None  # defaults to the Flask instance folder
    preload_speech_model: bool = False

    # Limits
    rate_limit_per_minute: int = 20  # 0 disables rate limiting
    max_message_chars: int = 2000
    max_history_turns: int = 6

    # Server
    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False

    @property
    def vosk_model_url(self) -> str:
        return f"https://alphacephei.com/vosk/models/{self.vosk_model_name}.zip"

    @classmethod
    def from_env(cls) -> "Config":
        mode = _env_str("AI_MODE", "auto").lower()
        if mode not in VALID_AI_MODES:
            mode = "auto"
        models_dir = os.getenv("SPEECH_MODELS_DIR", "").strip()
        return cls(
            gemini_api_key=_clean_key(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
            gemini_model=_env_str("GEMINI_MODEL", cls.gemini_model),
            ollama_host=_env_str("OLLAMA_HOST", cls.ollama_host),
            ollama_model=_env_str("OLLAMA_MODEL", cls.ollama_model),
            ai_mode=mode,
            request_timeout=_env_int("REQUEST_TIMEOUT", cls.request_timeout, minimum=1),
            speech_lang=_env_str("SPEECH_LANG", cls.speech_lang),
            vosk_model_name=_env_str("VOSK_MODEL_NAME", cls.vosk_model_name),
            models_dir=Path(models_dir) if models_dir else None,
            preload_speech_model=_env_bool("PRELOAD_SPEECH_MODEL", True),
            rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", cls.rate_limit_per_minute),
            host=_env_str("FLASK_HOST", cls.host),
            port=_env_int("FLASK_PORT", cls.port, minimum=1),
            debug=_env_bool("FLASK_DEBUG", False),
        )
