"""Offline speech-to-text using a locally stored Vosk model.

The model is downloaded in a background thread (optionally at start-up) so that no request
has to wait for it. Progress is exposed through ``status()`` for the UI to display.
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import wave
import zipfile
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MAX_AUDIO_SECONDS = 60
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_UNPACKED_BYTES = 250 * 1024 * 1024


class SpeechModelNotReady(Exception):
    """The Vosk model has not been downloaded yet."""


class SpeechModelError(Exception):
    """The model could not be downloaded, unpacked or loaded. Message is safe to show."""


class InvalidAudio(ValueError):
    """The uploaded audio is unusable. Message is safe to show."""


def decode_wav(data: bytes) -> bytes:
    """Validate a mono, 16-bit, 16 kHz WAV upload and return its raw PCM frames."""
    if len(data) < 44:
        raise InvalidAudio("No recorded audio was received.")
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getframerate() != SAMPLE_RATE:
                raise InvalidAudio("Audio must be mono, 16-bit WAV at 16 kHz.")
            if audio.getnframes() == 0:
                raise InvalidAudio("The recording was empty.")
            if audio.getnframes() / SAMPLE_RATE > MAX_AUDIO_SECONDS:
                raise InvalidAudio(f"Recordings must be {MAX_AUDIO_SECONDS} seconds or shorter.")
            return audio.readframes(audio.getnframes())
    except (EOFError, wave.Error) as error:
        raise InvalidAudio("The recorded audio is not a valid WAV file.") from error


def safe_extract(archive_path: Path, destination: Path) -> None:
    """Unzip ``archive_path`` into ``destination``, refusing oversized or path-traversing archives."""
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if sum(member.file_size for member in members) > MAX_UNPACKED_BYTES:
            raise SpeechModelError("The offline speech model archive is larger than expected.")
        for member in members:
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
                raise SpeechModelError("The offline speech model archive contains an unsafe path.")
        archive.extractall(destination)


class OfflineSpeechModel:
    """Manages download, loading and use of one Vosk model."""

    def __init__(self, models_dir: Path, name: str, url: str):
        self.models_dir = Path(models_dir)
        self.name = name
        self.url = url
        self.model_path = self.models_dir / name
        self._model = None
        self._model_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._state = {"state": "missing", "progress": 0, "message": "Offline speech model not downloaded yet."}
        if self.model_path.is_dir():
            self._state = {"state": "ready", "progress": 100, "message": "Offline speech model ready."}

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        with self._state_lock:
            return {**self._state, "model": self.name}

    def _set(self, **fields) -> None:
        with self._state_lock:
            self._state.update(fields)

    # ---------------------------------------------------------------- download
    def start_download(self) -> bool:
        """Begin a background download. Returns False if already ready or in progress."""
        with self._state_lock:
            if self._state["state"] in ("ready", "downloading"):
                return False
            self._state = {"state": "downloading", "progress": 0, "message": "Downloading offline speech model..."}
        threading.Thread(target=self._download, name="vosk-model-download", daemon=True).start()
        return True

    def _download(self) -> None:
        try:
            self.models_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="speech-model-", dir=self.models_dir) as temp:
                archive = Path(temp) / "model.zip"
                self._fetch(archive)
                safe_extract(archive, Path(temp))
                extracted = Path(temp) / self.name
                if not extracted.is_dir():
                    raise SpeechModelError("The offline speech model archive did not contain the expected model.")
                if not self.model_path.exists():  # another process may have finished first
                    shutil.move(str(extracted), str(self.model_path))
            self._set(state="ready", progress=100, message="Offline speech model ready.")
            log.info("Offline speech model installed at %s", self.model_path)
        except SpeechModelError as error:
            log.warning("Speech model install failed: %s", error)
            self._set(state="error", message=str(error))
        except (OSError, urllib.error.URLError, zipfile.BadZipFile) as error:
            log.warning("Speech model download failed: %s", error)
            self._set(
                state="error",
                message="Could not download the offline speech model. Connect to the internet and try again.",
            )

    def _fetch(self, target: Path) -> None:
        with urllib.request.urlopen(self.url, timeout=60) as response:  # noqa: S310 (https URL from config)
            try:
                total = int(response.headers.get("Content-Length") or 0)
            except ValueError:
                total = 0
            if total > MAX_DOWNLOAD_BYTES:
                raise SpeechModelError("The offline speech model download is larger than expected.")
            downloaded = 0
            with target.open("wb") as out:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise SpeechModelError("The offline speech model download exceeded the allowed size.")
                    out.write(chunk)
                    if total:
                        self._set(progress=min(99, int(downloaded * 100 / total)))

    # ----------------------------------------------------------- transcription
    def _get_model(self):
        with self._model_lock:
            if self._model is None:
                if not self.model_path.is_dir():
                    raise SpeechModelNotReady("The offline speech model has not been downloaded yet.")
                try:
                    from vosk import Model, SetLogLevel

                    SetLogLevel(-1)
                    self._model = Model(str(self.model_path))
                except ImportError as error:
                    raise SpeechModelError("The 'vosk' package is not installed.") from error
                except Exception as error:  # vosk raises a bare Exception on a bad model
                    log.exception("Could not load the Vosk model")
                    raise SpeechModelError("The offline speech model could not be loaded.") from error
            return self._model

    def transcribe(self, pcm_frames: bytes) -> str:
        model = self._get_model()
        from vosk import KaldiRecognizer

        recognizer = KaldiRecognizer(model, SAMPLE_RATE)
        recognizer.AcceptWaveform(pcm_frames)
        return json.loads(recognizer.FinalResult()).get("text", "").strip()
