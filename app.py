"""Entry point: ``python app.py`` (development) or ``flask --app app run``."""
import logging
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)  # always the .env next to app.py, whatever folder the terminal is in

from chatbot import create_app  # noqa: E402  (must come after load_dotenv)
from chatbot.config import Config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

config = Config.from_env()
app = create_app(config)
log = logging.getLogger("startup")


def report_key_status() -> None:
    """Say plainly whether the Gemini key was found, without ever printing the key."""
    if config.gemini_api_key:
        log.info("Gemini API key found (model %s).", config.gemini_model)
    elif not ENV_FILE.exists():
        log.warning("No .env file found. Copy .env.example to .env (same folder as app.py) and add GEMINI_API_KEY.")
    else:
        log.warning("%s exists but GEMINI_API_KEY is empty. Paste your key after GEMINI_API_KEY= and save.", ENV_FILE.name)


report_key_status()

if __name__ == "__main__":
    app.run(host=config.host, port=config.port, debug=config.debug)
