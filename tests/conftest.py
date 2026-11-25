import pytest

from chatbot import create_app
from chatbot.config import Config


@pytest.fixture
def make_app(tmp_path):
    def factory(**overrides):
        settings = dict(
            gemini_api_key=None,
            ai_mode="simulated",
            models_dir=tmp_path / "models",
            preload_speech_model=False,
            rate_limit_per_minute=0,
        )
        settings.update(overrides)
        return create_app(Config(**settings))

    return factory


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()
