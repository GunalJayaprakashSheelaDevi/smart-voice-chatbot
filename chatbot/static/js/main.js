// Page controller: chat, status display, and wiring of voice input / read-aloud.
import { getStatus, sendChat } from "./api.js";
import { initTextToSpeech } from "./tts.js";
import { initVoiceInput } from "./voice-input.js";

const $ = (id) => document.getElementById(id);
const chatBox = $("chat-box");
const userInput = $("user-input");
const sendButton = $("send-btn");
const engineSelect = $("engine-mode");
const styleSelect = $("answer-style");
const simplerButton = $("simpler-btn");
const GREETING = "Hello! You can type a question or click Speak to use voice input.";
const SIMPLER_REQUEST = "Please explain your last answer more simply, with an everyday example.";
const voiceStatus = $("voice-status");
const speechLang = document.body.dataset.speechLang || "en-GB";

const ENGINE_LABELS = { gemini: "Gemini (cloud)", ollama: "Local model (Ollama)", simulated: "Demo mode" };
const MAX_CLIENT_HISTORY = 12;

let history = [];
let sending = false;
let epoch = 0; // bumped by New conversation so a late reply from the old chat is ignored
const firstReply = chatBox.querySelector(".msg-ai .msg-text");
let latestReply = firstReply ? firstReply.textContent.trim() : "";

// ---- Chat ------------------------------------------------------------------
// Messages are built with textContent only, so model output can never inject HTML.
function addMessage(sender, message, roleClass = "msg-ai", badgeText = "") {
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${roleClass}`;

    const identity = document.createElement("span");
    identity.className = "msg-identity";
    const avatar = document.createElement("span");
    const isUser = roleClass === "msg-user";
    avatar.className = `avatar ${isUser ? "avatar-human" : "avatar-robot"}`;
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = isUser ? "🧑‍💻" : "🤖";
    const name = document.createElement("strong");
    name.textContent = `${sender}: `;
    identity.append(avatar, name);
    wrapper.appendChild(identity);

    if (badgeText) {
        const tag = document.createElement("span");
        tag.className = "inline-tag";
        tag.textContent = badgeText;
        wrapper.append(tag, document.createTextNode(" "));
    }

    const text = document.createElement("span");
    text.className = "msg-text";
    text.textContent = message;
    wrapper.appendChild(text);

    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
    return wrapper;
}

const speaker = initTextToSpeech({
    button: $("tts-btn"),
    getText: () => latestReply,
    lang: speechLang,
    onError: (message) => {
        voiceStatus.textContent = message;
    },
});

async function sendMessage(overrideText) {
    const message = (typeof overrideText === "string" ? overrideText : userInput.value).trim();
    if (!message || sending) return;

    const myEpoch = epoch;
    sending = true;
    sendButton.disabled = true;
    addMessage("You", message, "msg-user");
    userInput.value = "";
    const thinking = addMessage("AI Assistant", "Thinking...", "msg-thinking");

    try {
        const data = await sendChat({ message, history, mode: engineSelect.value, style: styleSelect.value });
        if (myEpoch !== epoch) return;
        thinking.remove();

        const label = ENGINE_LABELS[data.engine] || data.engine;
        addMessage("AI Assistant", data.reply, "msg-ai", data.fallback ? `Auto-fallback: ${label}` : label);

        speaker.stop();
        latestReply = data.reply;
        simplerButton.disabled = false;
        history.push({ role: "user", text: message }, { role: "assistant", text: data.reply });
        history = history.slice(-MAX_CLIENT_HISTORY);
    } catch (error) {
        if (myEpoch !== epoch) return;
        thinking.remove();
        addMessage("AI Assistant", error.message, "msg-error");
    } finally {
        sending = false;
        sendButton.disabled = false;
        userInput.focus();
    }
}

sendButton.addEventListener("click", () => sendMessage());
userInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.isComposing) sendMessage();
});

// ---- Repair and reset ----------------------------------------

// Repair turn: the person corrects a misunderstanding in one action.
simplerButton.addEventListener("click", () => sendMessage(SIMPLER_REQUEST));

// Session-only memory: nothing is stored, and this clears what the page holds.
$("reset-btn").addEventListener("click", () => {
    speaker.stop();
    epoch += 1;
    history = [];
    sending = false;
    sendButton.disabled = false;
    chatBox.replaceChildren();
    addMessage("AI Assistant", GREETING);
    latestReply = GREETING;
    simplerButton.disabled = true;
    userInput.focus();
});

// ---- Voice input -----------------------------------------------------------
initVoiceInput({
    button: $("voice-btn"),
    modeSelect: $("speech-mode"),
    statusEl: voiceStatus,
    lang: speechLang,
    onTranscript: (text) => {
        userInput.value = text;
        sendMessage();
    },
    onProblem: (message) => addMessage("AI Assistant", message, "msg-error"),
});

// ---- Status pills ----------------------------------------------------------
function setPill(id, text, level) {
    const pill = $(id);
    pill.textContent = text;
    pill.className = `pill pill-${level}`;
}

function renderStatus(status) {
    const { gemini, ollama } = status.engines;
    setPill("pill-cloud", gemini.available ? `Cloud AI: ready (${gemini.model})` : "Cloud AI: add key to .env", gemini.available ? "ok" : "warn");
    $("pill-local").hidden = !ollama.available;  // optional engine: only shown when it is running
    setPill("pill-local", `Local model: ready (${ollama.model})`, "ok");

    const speech = status.speech_model;
    const speechText = {
        ready: ["Offline speech: ready", "ok"],
        downloading: [`Offline speech: downloading ${speech.progress}%`, "warn"],
        missing: ["Offline speech: not downloaded", "warn"],
        error: ["Offline speech: download failed", "bad"],
    }[speech.state] || ["Offline speech: unknown", "warn"];
    setPill("pill-speech", ...speechText);
    return speech.state === "downloading";
}

async function refreshStatus() {
    let downloading = false;
    try {
        downloading = renderStatus(await getStatus());
    } catch {
        ["pill-cloud", "pill-local", "pill-speech"].forEach((id) => setPill(id, "Server unreachable", "bad"));
    }
    setTimeout(refreshStatus, downloading ? 1500 : 15000);
}

refreshStatus();
