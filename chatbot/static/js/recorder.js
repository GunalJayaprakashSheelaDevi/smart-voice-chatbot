// Microphone capture for offline speech mode. Uses an AudioWorklet where available
// and falls back to the older ScriptProcessor API.
import { createWavBlob } from "./wav.js";

const AudioContextCtor = window.AudioContext || window.webkitAudioContext;

export const supportsRecording = Boolean(
    navigator.mediaDevices &&
        AudioContextCtor &&
        (typeof AudioContextCtor.prototype.createScriptProcessor === "function" ||
            "audioWorklet" in AudioContextCtor.prototype)
);

const WORKLET_CODE = `
class SpeechCaptureProcessor extends AudioWorkletProcessor {
    process(inputs) {
        const channels = inputs[0];
        if (channels && channels.length > 0) {
            const mono = new Float32Array(channels[0].length);
            for (let c = 0; c < channels.length; c += 1) {
                for (let i = 0; i < mono.length; i += 1) {
                    mono[i] += channels[c][i] / channels.length;
                }
            }
            this.port.postMessage(mono, [mono.buffer]);
        }
        return true;
    }
}
registerProcessor("speech-capture-processor", SpeechCaptureProcessor);
`;

export class Recorder {
    #stream = null;
    #context = null;
    #source = null;
    #processor = null;
    #mute = null;
    #chunks = [];

    async start() {
        this.#chunks = [];
        this.#stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        try {
            this.#context = new AudioContextCtor();
            await this.#context.resume();
            this.#source = this.#context.createMediaStreamSource(this.#stream);
            this.#processor = await this.#createProcessor();

            // Route through a silent gain node so the processor runs without echoing the mic.
            this.#mute = this.#context.createGain();
            this.#mute.gain.value = 0;
            this.#source.connect(this.#processor);
            this.#processor.connect(this.#mute);
            this.#mute.connect(this.#context.destination);
        } catch (error) {
            await this.cancel();
            throw error;
        }
    }

    /** Stops capturing and returns the recording as a 16 kHz mono WAV Blob. */
    async stop() {
        const chunks = this.#chunks;
        const sampleRate = this.#context ? this.#context.sampleRate : 16000;
        await this.#teardown();
        return createWavBlob(chunks, sampleRate);
    }

    /** Releases the microphone without producing audio. Safe to call at any time. */
    async cancel() {
        await this.#teardown();
    }

    async #createProcessor() {
        const context = this.#context;
        if (context.audioWorklet && window.AudioWorkletNode) {
            const url = URL.createObjectURL(new Blob([WORKLET_CODE], { type: "application/javascript" }));
            try {
                await context.audioWorklet.addModule(url);
            } finally {
                URL.revokeObjectURL(url);
            }
            const node = new AudioWorkletNode(context, "speech-capture-processor", {
                numberOfInputs: 1,
                numberOfOutputs: 1,
                outputChannelCount: [1],
            });
            node.port.onmessage = (event) => this.#chunks.push(new Float32Array(event.data));
            return node;
        }

        const node = context.createScriptProcessor(4096, 1, 1);
        node.onaudioprocess = (event) => {
            const input = event.inputBuffer;
            const mono = new Float32Array(input.length);
            for (let c = 0; c < input.numberOfChannels; c += 1) {
                const data = input.getChannelData(c);
                for (let i = 0; i < data.length; i += 1) mono[i] += data[i] / input.numberOfChannels;
            }
            this.#chunks.push(mono);
        };
        return node;
    }

    async #teardown() {
        if (this.#processor) {
            if (this.#processor.port) this.#processor.port.onmessage = null;
            if ("onaudioprocess" in this.#processor) this.#processor.onaudioprocess = null;
        }
        for (const node of [this.#source, this.#processor, this.#mute]) {
            try {
                node?.disconnect();
            } catch {
                // Already disconnected.
            }
        }
        this.#stream?.getTracks().forEach((track) => track.stop());
        if (this.#context && this.#context.state !== "closed") {
            await this.#context.close();
        }
        this.#stream = this.#context = this.#source = this.#processor = this.#mute = null;
        this.#chunks = [];
    }
}
