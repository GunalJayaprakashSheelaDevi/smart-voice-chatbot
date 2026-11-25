// Thin wrappers around the Flask JSON API. Every function rejects with an Error
// whose message is safe to show to the user.

async function request(path, options) {
    let response;
    try {
        response = await fetch(path, options);
    } catch {
        throw new Error("Network error: could not reach the Flask server.");
    }

    let data = {};
    try {
        data = await response.json();
    } catch {
        // Non-JSON error body; fall through to the generic message below.
    }
    if (!response.ok) {
        throw new Error(data.error || `Request failed (${response.status}).`);
    }
    return data;
}

export const getStatus = () => request("/api/status");

export const prepareSpeechModel = () => request("/api/speech/prepare", { method: "POST" });

export const sendChat = (payload) =>
    request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

export const transcribe = (wavBlob) =>
    request("/api/transcribe", {
        method: "POST",
        headers: { "Content-Type": "audio/wav" },
        body: wavBlob,
    });
