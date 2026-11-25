"""Validation of incoming chat requests.

The client sends the conversation as structured ``{"role", "text"}`` items. Roles are
checked against a fixed allow-list so a forged entry such as ``"System"`` is rejected
instead of being pasted into the prompt.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import VALID_AI_MODES, Config

ALLOWED_ROLES = {"user", "assistant"}
ALLOWED_STYLES = ("simple", "detailed")


class ValidationError(ValueError):
    """Raised when a request is malformed. The message is safe to show to the user."""


@dataclass(frozen=True)
class ChatRequest:
    message: str
    history: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": str}]
    mode: str
    style: str = "simple"


def parse_chat_request(payload: object, config: Config) -> ChatRequest:
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")

    message = payload.get("message", "")
    if not isinstance(message, str):
        raise ValidationError("'message' must be a string.")
    message = message.strip()
    if not message:
        raise ValidationError("Please enter or speak a question first.")
    if len(message) > config.max_message_chars:
        raise ValidationError(f"Messages must be {config.max_message_chars} characters or fewer.")

    mode = str(payload.get("mode") or config.ai_mode).lower()
    if mode not in VALID_AI_MODES:
        raise ValidationError(f"'mode' must be one of: {', '.join(VALID_AI_MODES)}.")

    style = str(payload.get("style") or "simple").lower()
    if style not in ALLOWED_STYLES:
        raise ValidationError(f"'style' must be one of: {', '.join(ALLOWED_STYLES)}.")

    return ChatRequest(message=message, history=_clean_history(payload.get("history"), config), mode=mode, style=style)


def _clean_history(raw: object, config: Config) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("'history' must be a list.")

    limit = config.max_history_turns * 2
    recent = raw[-limit:] if limit else []

    cleaned: list[dict[str, str]] = []
    for item in recent:
        if not isinstance(item, dict):
            raise ValidationError("Each history entry must be an object.")
        role = str(item.get("role", "")).strip().lower()
        if role not in ALLOWED_ROLES:
            raise ValidationError("History roles must be 'user' or 'assistant'.")
        text = item.get("text")
        if not isinstance(text, str):
            raise ValidationError("Each history entry needs a text string.")
        text = text.strip()[: config.max_message_chars]
        if text:
            cleaned.append({"role": role, "content": text})

    # Chat APIs expect a conversation to start with the user.
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    return cleaned
