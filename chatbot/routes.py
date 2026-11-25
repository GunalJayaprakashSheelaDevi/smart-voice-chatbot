"""HTTP routes: one page plus a small JSON API under /api."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import wraps
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request

from .config import Config
from .providers import ChatResult, OllamaProbe, ProviderUnavailable, generate_reply
from .ratelimit import RateLimiter
from .speech import InvalidAudio, OfflineSpeechModel, SpeechModelError, SpeechModelNotReady, decode_wav
from .validation import ValidationError, parse_chat_request

bp = Blueprint("main", __name__)


@dataclass
class Services:
    """Everything the routes need, created once in create_app()."""

    config: Config
    gemini_client: Any | None
    speech: OfflineSpeechModel
    ollama_probe: OllamaProbe
    limiter: RateLimiter


def _services() -> Services:
    return current_app.extensions["chatbot"]


def rate_limited(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _services().limiter.allow(request.remote_addr or "unknown"):
            return jsonify(error="Too many requests. Please wait a moment and try again."), 429
        return view(*args, **kwargs)

    return wrapper


@bp.get("/")
def home():
    return render_template("index.html", speech_lang=_services().config.speech_lang)


@bp.get("/api/status")
def status():
    services = _services()
    config = services.config
    return jsonify(
        {
            "default_mode": config.ai_mode,
            "speech_lang": config.speech_lang,
            "engines": {
                "gemini": {"available": services.gemini_client is not None, "model": config.gemini_model},
                "ollama": {"available": services.ollama_probe.available(), "model": config.ollama_model},
                "simulated": {"available": True},
            },
            "speech_model": services.speech.status(),
        }
    )


@bp.post("/api/chat")
@rate_limited
def chat():
    services = _services()
    try:
        parsed = parse_chat_request(request.get_json(silent=True), services.config)
    except ValidationError as error:
        return jsonify(error=str(error)), 400

    try:
        result: ChatResult = generate_reply(services.config, services.gemini_client, parsed)
    except ProviderUnavailable as error:
        return jsonify(error=str(error)), 502
    return jsonify(reply=result.reply, engine=result.engine, fallback=result.fallback)


@bp.post("/api/speech/prepare")
def prepare_speech():
    """Start the offline model download in the background; the UI polls /api/status."""
    speech = _services().speech
    speech.start_download()
    return jsonify(speech_model=speech.status()), 202


@bp.post("/api/transcribe")
@rate_limited
def transcribe():
    try:
        frames = decode_wav(request.get_data(cache=False))
    except InvalidAudio as error:
        return jsonify(error=str(error)), 400

    try:
        text = _services().speech.transcribe(frames)
    except (SpeechModelNotReady, SpeechModelError) as error:
        return jsonify(error=str(error)), 503
    except (RuntimeError, json.JSONDecodeError):
        current_app.logger.exception("Offline speech transcription failed")
        return jsonify(error="Offline speech transcription failed. Please try again."), 500
    return jsonify(text=text)
