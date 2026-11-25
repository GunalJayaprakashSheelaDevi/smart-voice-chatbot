// Voice input with two interchangeable back ends:
//   "browser" - the browser's SpeechRecognition service (needs internet)
//   "offline" - record a WAV here and transcribe on the server with Vosk
import { getStatus, prepareSpeechModel, transcribe } from "./api.js";
import { Recorder, supportsRecording } from "./recorder.js";

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
const IDLE_LABEL = "🎤 Speak";
const MAX_RECORDING_MS = 60_000;
const MODEL_WAIT_LIMIT_MS = 10 * 60_000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function recognitionErrorMessage(code, lang) {
    const messages = {
        "no-speech": "No speech detected. Check your microphone, then click Speak and try again.",
        "audio-capture": "No microphone found. Connect or enable a microphone, or type your question instead.",
        "not-allowed": "Microphone permission blocked. Allow microphone access in your browser site settings.",
        "service-not-allowed": "The browser blocked speech recognition. Check site permissions or use text input.",
        network: "The browser speech service needs an internet connection. Choose Offline mode to transcribe on this computer.",
        "language-not-supported": `The speech language (${lang}) is not supported in this browser.`,
        aborted: "Listening stopped before speech completed. Click Speak to try again.",
    };
    return messages[code] || "Voice input could not start. Check permissions or type your question.";
}

function microphoneErrorMessage(error) {
    if (error && error.name === "NotAllowedError") {
        return "Microphone permission blocked. Allow microphone access in your browser site settings.";
    }
    if (error && error.name === "NotFoundError") {
        return "No microphone found. Connect or enable a microphone, or type your question instead.";
    }
    return (error && error.message) || "Offline speech could not start.";
}

export function initVoiceInput({ button, modeSelect, statusEl, lang, onTranscript, onProblem }) {
    const recorder = new Recorder();
    let recognition = null;
    let recording = false;
    let recordingTimer = null;

    const setStatus = (text) => {
        statusEl.textContent = text;
    };
    const setIdle = () => {
        button.disabled = false;
        modeSelect.disabled = false;
        button.textContent = IDLE_LABEL;
    };

    // ---- Online (browser) ------------------------------------------------
    if (SpeechRecognitionCtor) {
        recognition = new SpeechRecognitionCtor();
        recognition.lang = lang;
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            setStatus(`Heard: "${transcript}"`);
            onTranscript(transcript);
        };
        recognition.onerror = (event) => {
            setStatus("Voice input encountered an issue. Text input remains available.");
            onProblem(recognitionErrorMessage(event.error, lang));
        };
        recognition.onend = setIdle;
    }

    function startOnline() {
        button.disabled = true;
        button.textContent = "Listening...";
        setStatus("Listening via the browser speech service...");
        try {
            recognition.start();
        } catch (error) {
            setIdle();
            onProblem(
                error.name === "InvalidStateError"
                    ? "Voice recognition is already active. Please wait a moment."
                    : recognitionErrorMessage(error.name, lang)
            );
        }
    }

    // ---- Offline (Vosk) --------------------------------------------------
    async function waitForSpeechModel() {
        let model = (await getStatus()).speech_model;
        if (model.state !== "ready" && model.state !== "downloading") {
            model = (await prepareSpeechModel()).speech_model;
        }
        const deadline = Date.now() + MODEL_WAIT_LIMIT_MS;
        while (model.state === "downloading") {
            setStatus(`Downloading the offline speech model (one time only)... ${model.progress}%`);
            if (Date.now() > deadline) throw new Error("The speech model download timed out. Please try again.");
            await sleep(1000);
            model = (await getStatus()).speech_model;
        }
        if (model.state !== "ready") {
            throw new Error(model.message || "The offline speech model is unavailable.");
        }
    }

    async function startOffline() {
        button.disabled = true;
        modeSelect.disabled = true;
        button.textContent = "Preparing...";
        setStatus("Preparing offline speech recognition...");

        await waitForSpeechModel();
        await recorder.start();

        recording = true;
        recordingTimer = setTimeout(() => stopOffline(true), MAX_RECORDING_MS);
        button.disabled = false;
        button.textContent = "⏹ Stop";
        setStatus("Recording offline. Click Stop when you have finished speaking.");
    }

    async function stopOffline(maxDurationReached = false) {
        if (!recording) return;
        recording = false;
        clearTimeout(recordingTimer);
        button.disabled = true;
        button.textContent = "Transcribing...";
        setStatus(maxDurationReached ? "Maximum recording time reached. Transcribing locally..." : "Transcribing locally...");

        try {
            const wavBlob = await recorder.stop();
            const data = await transcribe(wavBlob);
            if (!data.text) {
                setStatus("No speech detected. Click Speak and try again.");
                return;
            }
            setStatus(`Heard: "${data.text}"`);
            onTranscript(data.text);
        } catch (error) {
            setStatus("Offline speech transcription failed.");
            onProblem(error.message);
        } finally {
            setIdle();
        }
    }

    // ---- Wiring ----------------------------------------------------------
    const onlineOption = modeSelect.querySelector('option[value="browser"]');
    const offlineOption = modeSelect.querySelector('option[value="offline"]');
    onlineOption.disabled = !recognition;
    offlineOption.disabled = !supportsRecording;
    if (!recognition && supportsRecording) modeSelect.value = "offline";
    if (!recognition && !supportsRecording) {
        button.disabled = true;
        setStatus("This browser does not support voice input. Please type your question instead.");
    }

    modeSelect.addEventListener("change", () => {
        setStatus(
            modeSelect.value === "offline"
                ? "Offline mode transcribes on this computer. The US English model downloads once, on first use."
                : `Online mode uses the browser speech service (${lang}) and needs an internet connection.`
        );
    });

    button.addEventListener("click", async () => {
        if (modeSelect.value === "offline") {
            if (recording) {
                await stopOffline();
                return;
            }
            try {
                await startOffline();
            } catch (error) {
                await recorder.cancel();
                recording = false;
                setIdle();
                setStatus("Offline speech could not start.");
                onProblem(microphoneErrorMessage(error));
            }
            return;
        }
        if (recognition) startOnline();
    });
}
