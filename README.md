# Smart Voice and Text AI Chatbot

**README prose word count:** about 821 (code blocks and setup commands excluded)

A voice-first study assistant: type or speak a question, get an answer, and have it read aloud. Answers come from a cloud model (Gemini), a local model (Ollama) or a built-in demo handler, and every reply is labelled with the engine that produced it.

**Background:** my Assignment 1 review asked how the clarity and relevance of chatbot responses affect understanding and satisfaction. This prototype builds the controls a study of that question needs: answer style, a repair button, and visible context.

## Project status

- **Works (implemented):** text chat with the last six turns as context; short-and-simple or detailed answer style; an "Explain more simply" repair button; a New conversation button (nothing is stored between sessions); online voice input (browser speech recognition); offline voice input (local Vosk model, downloaded once in the background with progress); read-aloud with a Stop button; Gemini and Ollama engines; status indicators; input validation, rate limiting and 33 automated tests.
- **Simulated:** the demo handler. It answers only a few preset topics (greetings, study tips, how voice input works) and is labelled "Demo mode".
- **Unfinished (planned):** grounding answers in the student's own notes, streaming replies, automatic end-of-speech detection, and the Assignment 1 study with real students. The prototype has not been evaluated with users, and the clarifying-question behaviour is requested in the prompt but not yet tested.
- **Scope:** a local, single-user prototype, not a deployed service. "Offline" speech needs only the Vosk model; fully offline answers also need Ollama.

## Technology stack

- **Flask (Python 3.10+):** web server and JSON API (`chatbot/` package).
- **Google Gemini (`google-genai`):** cloud answers; needs your own API key.
- **Ollama (default `llama3.2:1b`):** optional local answers; undecided whether a larger model would be worth it.
- **Vosk (small US English model, Apache-2.0):** offline speech-to-text on the server.
- **Browser APIs:** `SpeechRecognition` (online speech input) and `speechSynthesis` (read aloud).
- **Front end:** plain HTML, CSS and JavaScript modules; no build step.
- **pytest:** automated tests.

## Running or inspecting the work

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
python app.py
```

Open http://127.0.0.1:5000 in Chrome or Edge.

- **No key needed to inspect it.** With no key and no Ollama the app runs in demo mode.
- **Supplying your own key.** Create a key in Google AI Studio and put it after `GEMINI_API_KEY=` in your local `.env`. This file is git-ignored; no key is stored in the repository.
- **Local model (optional).** Install Ollama and run `ollama pull llama3.2:1b`.
- **Tests.** `pip install -r requirements-dev.txt` then `pytest` (no network, key or speech model needed; 33 tests).
- **Design notes.** `docs/ARCHITECTURE.md` explains the request flow; `docs/CHANGELOG.md` lists fixes.

## Development record

1. **Core text chat:** Flask backend, `POST /chat`, input validation, safe DOM rendering. Commit: [add link]
2. **Voice input:** browser speech recognition with clear error messages. Commit: [add link]
3. **Fallback and context:** demo handler, status endpoint, multi-turn history. Commit: [add link]
4. **Offline speech:** local Vosk transcription with a one-time model download. Commit: [add link]
5. **Restructure and hardening:** after a code review found five problems (offline claim covered only speech; forgeable history roles; model download inside one request; no tests or rate limit; unclear purpose), I split the code into modules, added the Ollama engine, fixed-role history, rate limiting, a background download with progress, status indicators and tests. Checked with 27 tests and by running the app. Commit: [add link]
6. **Assignment 1 features:** after reading my literature review and the Week 1 to 4 lectures, I added answer style, the repair button, the accuracy notice and New conversation, with 6 more tests (33 in total). Commit: [add link]

## AI assistance

- **Tools:** Google Gemini (first version) and Claude (second version).
- **Gemini was used for:** reviewing security, refining speech error messages, drafting the first fallback handler and documentation.
- **Claude was used for:** code review, restructuring, the Ollama engine, tests, diagrams, storyboard sketches and drafting the report and README.
- **Examples of checking and changing:**
  - A review warned that history roles sent by the browser could be forged. I accepted this, added a role allow-list, and wrote tests that fail if a "System" role gets through.
  - The suggested fallback order was changed so that an explicitly chosen engine never falls back silently, so users always know what answered.
  - Claude proposed the Assignment 1 features (answer style, repair button) after I shared my review and lecture slides. [Confirm: describe what you decided or changed.]
  - A suggested newer Gemini model name was made configurable (`GEMINI_MODEL`) because model names change.
  - [Add one example of something you tested, changed or rejected yourself.]
- **Verification:** all code was read, the 33 tests were run, and the app was run locally. [Confirm the browser voice and read-aloud features you tested yourself.]

## Additional files

- `docs/Assignment_2_Project_Report.docx`: the project report (also submitted separately).
- No ZIP file is needed; everything else is in this repository.
