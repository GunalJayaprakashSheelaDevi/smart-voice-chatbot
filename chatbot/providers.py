"""AI engines: Gemini (cloud), Ollama (local) and a rule-based demo fallback."""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Config
from .validation import ChatRequest

log = logging.getLogger(__name__)

# The prompt is written as a small task specification: task, audience, constraints and output format.
BASE_PROMPT = (
    "You are a friendly study assistant inside a voice-and-text chatbot for students. "
    "Help them understand topics, plan revision and stay motivated. "
    "Answers are often read aloud, so reply in plain sentences with no markdown, bullet symbols or emoji. "
    "Answer the question that was asked and stay on the current topic. "
    "If a question is ambiguous, ask one short clarifying question instead of guessing. "
    "If you are unsure or cannot support a claim, say so instead of guessing."
)

STYLE_PROMPTS = {
    "simple": (
        "Use short sentences and everyday words, at roughly a sixth-grade reading level. "
        "Give the direct answer first and keep the whole reply under 100 words."
    ),
    "detailed": (
        "Give a fuller explanation in clear short paragraphs, with one brief example. "
        "Keep the whole reply under 250 words."
    ),
}


def build_system_prompt(style: str = "simple") -> str:
    return f"{BASE_PROMPT} {STYLE_PROMPTS.get(style, STYLE_PROMPTS['simple'])}"


ENGINE_CHAINS = {
    "auto": ("gemini", "ollama", "simulated"),
    "gemini": ("gemini",),
    "ollama": ("ollama",),
    "simulated": ("simulated",),
}


class ProviderUnavailable(Exception):
    """An engine could not produce an answer. The message is safe to show to the user."""


@dataclass(frozen=True)
class ChatResult:
    reply: str
    engine: str  # gemini | ollama | simulated
    fallback: bool  # True when a preferred engine failed and another one answered


# --------------------------------------------------------------------------- Gemini
def build_gemini_client(config: Config) -> Any | None:
    """Return a Gemini client, or None when no key is set or the SDK is missing."""
    if not config.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=config.gemini_api_key,
            http_options=types.HttpOptions(timeout=config.request_timeout * 1000),
        )
    except Exception:  # SDK missing or misconfigured: run without the cloud engine
        log.exception("Could not create the Gemini client; cloud engine disabled.")
        return None


FALLBACK_GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.1-flash-lite")  # tried in order if the main model fails


def _gemini_error_code(error: Exception) -> int | None:
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    return code if isinstance(code, int) else None


def explain_gemini_error(error: Exception) -> str:
    """Turn a Gemini SDK error into a short, safe message that says what to do."""
    code = _gemini_error_code(error)
    text = str(error).lower()
    if code in (400, 401, 403) or "api key" in text or "api_key" in text:
        return "Gemini rejected the API key. Create a new key at aistudio.google.com/apikey, put it in .env and restart the app."
    if code == 429 or "quota" in text or "resource_exhausted" in text:
        return "Gemini's free usage limit was reached. Wait about a minute and ask again."
    if code in (500, 502, 503, 504) or "unavailable" in text or "overloaded" in text:
        return "Gemini is busy right now. Please try again in a few seconds."
    if code == 404:
        return "The configured Gemini model was not found. Check GEMINI_MODEL in .env."
    return "Could not reach Gemini. Check your internet connection and try again."


def gemini_reply(client: Any, config: Config, history: list[dict[str, str]], message: str, style: str = "simple") -> str:
    from google.genai import types

    contents = [
        types.Content(role="user" if turn["role"] == "user" else "model", parts=[types.Part(text=turn["content"])])
        for turn in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    gen_config = types.GenerateContentConfig(system_instruction=build_system_prompt(style), max_output_tokens=700, temperature=0.6)
    text = ""
    last_error: Exception | None = None
    for model in dict.fromkeys((config.gemini_model, *FALLBACK_GEMINI_MODELS)):  # main model, then the others
        try:
            response = client.models.generate_content(model=model, contents=contents, config=gen_config)
            text = (response.text or "").strip()
            last_error = None
            break
        except Exception as error:  # the SDK raises many error types; classify below
            log.warning("Gemini request failed (model %s): %s", model, error)
            last_error = error
            if _gemini_error_code(error) in (400, 401, 403):  # key problem: another model will not help
                break
    if last_error is not None:
        raise ProviderUnavailable(explain_gemini_error(last_error)) from last_error
    if not text:
        raise ProviderUnavailable("Gemini returned an empty answer.")
    return text


# --------------------------------------------------------------------------- Ollama
def _request_json(url: str, payload: dict | None, timeout: float) -> dict:
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ProviderUnavailable("The Ollama address must start with http:// or https://.")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (scheme checked above)
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
        raise ProviderUnavailable(
            "The local Ollama model is not reachable. Start Ollama and pull the configured model."
        ) from error


def ollama_reply(config: Config, history: list[dict[str, str]], message: str, style: str = "simple") -> str:
    messages = [{"role": "system", "content": build_system_prompt(style)}, *history, {"role": "user", "content": message}]
    data = _request_json(
        f"{config.ollama_host.rstrip('/')}/api/chat",
        {"model": config.ollama_model, "messages": messages, "stream": False},
        timeout=config.request_timeout * 4,  # local models on CPU can be slow
    )
    text = str((data.get("message") or {}).get("content", "")).strip()
    if not text:
        raise ProviderUnavailable("The local model returned an empty answer.")
    return text


class OllamaProbe:
    """Cheap, cached check used by /api/status to show whether the local model is usable."""

    def __init__(self, config: Config, ttl: float = 10.0):
        self._config = config
        self._ttl = ttl
        self._lock = threading.Lock()
        self._checked_at = float("-inf")
        self._value = False

    def available(self) -> bool:
        with self._lock:
            if time.monotonic() - self._checked_at < self._ttl:
                return self._value
        value = self._check()
        with self._lock:
            self._value, self._checked_at = value, time.monotonic()
        return value

    def _check(self) -> bool:
        try:
            data = _request_json(f"{self._config.ollama_host.rstrip('/')}/api/tags", None, timeout=1.0)
        except ProviderUnavailable:
            return False
        names = {str(model.get("name", "")) for model in data.get("models", []) if isinstance(model, dict)}
        wanted = self._config.ollama_model
        return wanted in names or (":" not in wanted and f"{wanted}:latest" in names)


# ------------------------------------------------------------------------ Demo mode
def simulated_reply(message: str) -> str:
    """Rule-based replies so the app can be demonstrated with no key and no local model."""
    text = message.lower()
    words = set(text.replace("?", " ").replace(",", " ").replace(".", " ").split())

    if words & {"hello", "hi", "hey"}:
        return (
            "[Demo mode] Hello! I am the built-in demo assistant, so I can only answer a few topics. "
            "Add a Gemini API key in .env to answer any question."
        )
    if any(key in text for key in ("study", "revise", "revision", "exam", "memor")):
        return (
            "[Demo mode] Three study tips: work in focused 25-minute blocks with short breaks, "
            "test yourself instead of rereading, and spread topics over several days rather than cramming."
        )
    if any(key in text for key in ("voice", "microphone", "speak", "offline")):
        return (
            "[Demo mode] Choose Online to use your browser's speech recognition, or Offline to transcribe "
            "on this computer with Vosk. Either way, the transcript is sent to the chat backend as text."
        )
    if "how" in words and any(key in text for key in ("work", "built", "made")):
        return (
            "[Demo mode] Your message goes from the browser to the Flask backend, which tries Gemini first, "
            "then a local Ollama model, and finally this demo handler."
        )
    if words & {"thanks", "thank"}:
        return "[Demo mode] You're welcome! Good luck with your studies."
    return (
        "[Demo mode] I can only answer a few preset topics. For real answers, add a Gemini API key "
        "or start a local Ollama model, then ask again."
    )


# ------------------------------------------------------------------------ Dispatcher
def generate_reply(config: Config, gemini_client: Any | None, request: ChatRequest) -> ChatResult:
    """Answer ``request`` using the engine chain for its mode.

    ``auto`` tries Gemini, then Ollama, then the demo handler, and reports when it fell back.
    An explicitly chosen engine never silently swaps to another one: if it fails, the error is raised.
    """
    chain = ENGINE_CHAINS[request.mode]
    failed = False
    gemini_problem: str | None = None

    for engine in chain:
        try:
            if engine == "gemini":
                if gemini_client is None:
                    if request.mode == "auto":
                        continue  # not configured: skip quietly
                    raise ProviderUnavailable("No Gemini API key is configured.")
                reply = gemini_reply(gemini_client, config, request.history, request.message, request.style)
            elif engine == "ollama":
                reply = ollama_reply(config, request.history, request.message, request.style)
            else:
                if gemini_problem:  # a key is set but Gemini failed: say why instead of giving a fake answer
                    raise ProviderUnavailable(gemini_problem)
                reply = simulated_reply(request.message)
        except ProviderUnavailable as error:
            if engine == "gemini":
                gemini_problem = str(error)
            if request.mode != "auto" or engine == "simulated":
                raise
            log.info("Engine %s failed in auto mode: %s", engine, error)
            failed = True
            continue
        return ChatResult(reply=reply, engine=engine, fallback=failed)

    raise ProviderUnavailable("No AI engine could answer this request.")  # unreachable: chain ends in simulated
