// Text-to-speech ("Read Aloud") using the browser's speechSynthesis API.

const READ_LABEL = "🔊 Read Aloud";
const STOP_LABEL = "⏹ Stop Reading";

export function initTextToSpeech({ button, getText, lang, onError }) {
    const supported = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
    if (!supported) {
        button.disabled = true;
        button.textContent = "🔊 Read Aloud Unsupported";
        button.title = "Text-to-speech is not supported in this browser.";
        return { stop() {} };
    }

    let current = null;

    function reset() {
        current = null;
        button.textContent = READ_LABEL;
    }

    function stop() {
        if (!current) return;
        reset(); // clear first so the cancel-triggered error event is ignored
        window.speechSynthesis.cancel();
    }

    button.addEventListener("click", () => {
        if (current) {
            stop();
            return;
        }
        const text = getText();
        if (!text) return;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang;
        utterance.onend = () => {
            if (current === utterance) reset();
        };
        utterance.onerror = (event) => {
            if (current !== utterance) return;
            reset();
            if (event.error !== "interrupted" && event.error !== "canceled") {
                onError("Text-to-speech failed. Check that your browser has a speech voice available.");
            }
        };

        current = utterance;
        button.textContent = STOP_LABEL;
        window.speechSynthesis.speak(utterance);
    });

    return { stop };
}
