/**
 * PCM Capture AudioWorklet Processor
 *
 * Receives Float32 audio frames from the browser audio graph (typically 48kHz),
 * resamples to 16kHz, converts to Int16, and flushes 1280-byte chunks (640 samples
 * = 40ms at 16kHz) to the main thread via MessagePort.
 *
 * iFlytek RTASR expects: PCM 16kHz, 16-bit, mono, little-endian
 */

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    /** @type {Int16Array} */
    this._buffer = new Int16Array(640); // 640 samples = 40ms at 16kHz
    this._bufferOffset = 0;
    this._stopped = false;

    this.port.onmessage = (event) => {
      if (event.data === "stop") {
        this._stopped = true;
      }
    };
  }

  /**
   * @param {Float32Array[][]} inputs
   * @returns {boolean}
   */
  process(inputs) {
    if (this._stopped) return false;

    const input = inputs[0];
    if (!input || !input[0]) return true;

    const samples = input[0]; // Float32Array, 128 frames at sampleRate

    // Downsample ratio: sampleRate (usually 48000) → 16000
    const ratio = sampleRate / 16000;

    for (let i = 0; i < samples.length; i++) {
      // Only take every `ratio`-th sample (simple decimation)
      if (i % Math.round(ratio) !== 0) continue;

      // Float32 [-1, 1] → Int16 [-32768, 32767]
      const s = Math.max(-1, Math.min(1, samples[i]));
      this._buffer[this._bufferOffset++] = s < 0 ? s * 0x8000 : s * 0x7FFF;

      if (this._bufferOffset >= 640) {
        // Send 1280 bytes (640 Int16 samples) to main thread
        this.port.postMessage(this._buffer.buffer.slice(0));
        this._bufferOffset = 0;
      }
    }

    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
