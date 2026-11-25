# Architecture

## Overview

```
Browser                                   Flask server
-------                                   ------------
main.js  ---- POST /api/chat ----------->  routes.chat
  |                                          validation.parse_chat_request
  |                                          providers.generate_reply
  |                                            gemini -> ollama -> demo
voice-input.js                             
  online:  browser SpeechRecognition
  offline: recorder.js -> wav.js
           ---- POST /api/transcribe --->  routes.transcribe
                                             speech.decode_wav -> Vosk
status pills <--- GET /api/status ------   engine and model availability
tts.js: speechSynthesis reads replies aloud
```

## Request flow for a chat message

1. `main.js` sends `{message, history, mode, style}`, where `style` is `simple` or `detailed`. History items are `{role: "user" | "assistant", text}`.
2. `validation.py` checks types, trims length, rejects unknown roles and modes, and drops a leading assistant turn.
3. `providers.generate_reply` builds the system prompt from the style, then walks the engine chain for the mode. In `auto` that is Gemini, Ollama, demo. A specific mode never falls back.
4. The route returns `{reply, engine, fallback}` and the UI labels the reply with the engine that produced it.

## Key design decisions

| Decision | Reason |
|---|---|
| Application factory (`create_app`) | Lets tests build isolated apps with their own config |
| Frozen `Config` dataclass read from env | One place for settings; safe defaults for tests |
| Structured history with a role allow-list | Prevents prompt injection through forged "System:" lines |
| Explicit engine choice never falls back silently | The user always knows what produced a reply |
| Background Vosk download with progress | No request waits minutes on a first-use download |
| Local Ollama engine | Makes fully offline answers possible, not only offline speech |
| ES modules, no build step | Keeps the front end simple and dependency-free |
| In-memory rate limiter | Enough for a single-process demo; documented limitation |

## Known limitations

- Replies are not streamed; the full answer arrives at once.
- The demo handler only knows a few preset topics.
- The Vosk model is US English while online recognition defaults to en-GB, so the two modes can transcribe the same speech differently. Set `SPEECH_LANG=en-US` to align them.
- Browser support: online recognition works best in Chrome and Edge.
