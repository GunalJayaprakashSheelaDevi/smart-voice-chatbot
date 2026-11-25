# Changelog

## Restructure and hardening

Fixes for the issues found in the project review:

| Issue | Fix |
|---|---|
| "Offline" only covered speech; answers still needed the cloud | Added a local Ollama engine, status pills and honest README wording |
| No clear purpose or audience | Framed as a voice-first study assistant, with a system prompt tuned for spoken answers |
| Client-supplied history was pasted into one prompt string (role forgery) | Fixed role allow-list, structured multi-turn `contents`, length limits |
| Model download blocked a request for up to 120 s | Background download with progress shown in the UI; optional pre-download at start-up |
| Online used en-GB, offline used a US model, undocumented | One `SPEECH_LANG` setting, difference documented in the README |
| Dropdown defaulted to Offline while README led with Online | Online is the default in the UI and the README |
| Possibly retired default model name | Default changed to `gemini-3.5-flash-lite` (the 2.5 models are limited to existing users), configurable via `GEMINI_MODEL` |
| No rate limiting on `/chat` | Per-client sliding-window limiter returning HTTP 429 |
| Auto mode hid failures behind a canned echo reply | Demo handler gives topic answers; fallback is labelled in the UI |
| No tests | 27 pytest tests |
| Single 250-line `app.py` and one large `script.js` | Split into focused Python modules and ES modules |

Also added: a "Stop Reading" button fix for the cancel event, input length limit in the UI, a double-send guard, and all API routes moved under `/api`.

## Assignment 1 features

| Idea from Assignment 1 and the lectures | Change |
|---|---|
| Clarity: readability and concise versus detailed answers | Answer style control (short and simple by default, detailed on request); prompt rewritten as a task specification |
| Clarification and repair | "Explain more simply" button; prompt asks one clarifying question when a question is ambiguous |
| Recognition over recall; managing expectations | An "AI answers can be wrong" notice and an always-visible repair button |
| Memory that users can clear | New conversation button; nothing is stored between sessions |

3 new tests bring the suite to 30.
