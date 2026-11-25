"""Smart Voice and Text AI Chatbot - application factory."""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify

from .config import Config
from .providers import OllamaProbe, build_gemini_client
from .ratelimit import RateLimiter
from .routes import Services, bp
from .speech import OfflineSpeechModel


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # audio uploads are ~2 MB at most

    speech = OfflineSpeechModel(
        models_dir=config.models_dir or Path(app.instance_path),
        name=config.vosk_model_name,
        url=config.vosk_model_url,
    )
    app.extensions["chatbot"] = Services(
        config=config,
        gemini_client=build_gemini_client(config),
        speech=speech,
        ollama_probe=OllamaProbe(config),
        limiter=RateLimiter(config.rate_limit_per_minute),
    )
    app.register_blueprint(bp)

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="That upload is too large."), 413

    if config.preload_speech_model:
        speech.start_download()  # no-op when the model is already installed

    return app
