// Converts raw microphone samples into a mono, 16-bit, 16 kHz WAV file,
// which is the format the /api/transcribe endpoint (and Vosk) expects.

const TARGET_RATE = 16000;

export function createWavBlob(chunks, inputSampleRate) {
    const inputLength = chunks.reduce((length, chunk) => length + chunk.length, 0);
    const input = new Float32Array(inputLength);
    let offset = 0;
    for (const chunk of chunks) {
        input.set(chunk, offset);
        offset += chunk.length;
    }

    // Linear-interpolation resample to 16 kHz.
    const outputLength = Math.floor((inputLength * TARGET_RATE) / inputSampleRate);
    const samples = new Float32Array(outputLength);
    const ratio = inputSampleRate / TARGET_RATE;
    for (let i = 0; i < outputLength; i += 1) {
        const position = i * ratio;
        const lower = Math.floor(position);
        const upper = Math.min(lower + 1, inputLength - 1);
        const fraction = position - lower;
        samples[i] = input[lower] * (1 - fraction) + input[upper] * fraction;
    }

    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeString = (at, text) => {
        for (let i = 0; i < text.length; i += 1) view.setUint8(at + i, text.charCodeAt(i));
    };

    writeString(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true); // PCM header size
    view.setUint16(20, 1, true); // PCM format
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, TARGET_RATE, true);
    view.setUint32(28, TARGET_RATE * 2, true); // byte rate
    view.setUint16(32, 2, true); // block align
    view.setUint16(34, 16, true); // bits per sample
    writeString(36, "data");
    view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(44 + i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
    }
    return new Blob([buffer], { type: "audio/wav" });
}
