import zipfile

import pytest

from chatbot.config import Config
from chatbot.ratelimit import RateLimiter
from chatbot.speech import InvalidAudio, OfflineSpeechModel, SpeechModelError, decode_wav, safe_extract
from chatbot.validation import ValidationError, parse_chat_request


def test_history_is_trimmed_and_starts_with_user():
    config = Config(max_history_turns=1)
    history = [
        {"role": "user", "text": "old"},
        {"role": "assistant", "text": "old reply"},
        {"role": "user", "text": "recent"},
        {"role": "assistant", "text": "recent reply"},
    ]
    parsed = parse_chat_request({"message": "x", "history": history}, config)
    assert [turn["content"] for turn in parsed.history] == ["recent", "recent reply"]


def test_history_drops_leading_assistant_turn():
    parsed = parse_chat_request({"message": "x", "history": [{"role": "assistant", "text": "hi"}]}, Config())
    assert parsed.history == []


def test_history_must_be_a_list():
    with pytest.raises(ValidationError):
        parse_chat_request({"message": "x", "history": "oops"}, Config())


def test_rate_limiter_window_expires():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # separate client
    now[0] = 61
    assert limiter.allow("a")


def test_rate_limiter_disabled_when_limit_is_zero():
    limiter = RateLimiter(limit=0)
    assert all(limiter.allow("a") for _ in range(100))


def test_decode_wav_rejects_garbage():
    with pytest.raises(InvalidAudio):
        decode_wav(b"not a wav file at all, but long enough to pass the size check....")


def test_safe_extract_blocks_path_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "x")
    with pytest.raises(SpeechModelError):
        safe_extract(archive, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_speech_model_detects_existing_install(tmp_path):
    (tmp_path / "my-model").mkdir()
    model = OfflineSpeechModel(tmp_path, "my-model", "https://example.invalid/m.zip")
    assert model.status()["state"] == "ready"


def test_api_key_is_trimmed_of_spaces_and_quotes(monkeypatch):
    from chatbot.config import Config

    monkeypatch.setenv("GEMINI_API_KEY", '  "abc123"  ')
    assert Config.from_env().gemini_api_key == "abc123"
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert Config.from_env().gemini_api_key is None
