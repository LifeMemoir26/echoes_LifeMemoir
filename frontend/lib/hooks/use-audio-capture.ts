"use client";

import { useCallback, useRef, useState } from "react";

export type AudioCaptureState = "idle" | "recording" | "error";

/**
 * Hook for capturing PCM audio from the microphone via AudioWorklet.
 *
 * Outputs 1280-byte Int16 PCM chunks (640 samples = 40ms at 16kHz) suitable
 * for streaming to iFlytek RTASR.
 */
export function useAudioCapture(onChunk: (chunk: ArrayBuffer) => void) {
  const [state, setState] = useState<AudioCaptureState>("idle");
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);

  const start = useCallback(async () => {
    try {
      setError(null);

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 48000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const ctx = new AudioContext({ sampleRate: 48000 });
      contextRef.current = ctx;

      // Resume the AudioContext explicitly — Chrome may create it in "suspended"
      // state when the audio worklet is set up after an async user-gesture chain.
      if (ctx.state === "suspended") {
        await ctx.resume();
      }

      await ctx.audioWorklet.addModule("/worklets/pcm-capture-processor.js");

      const source = ctx.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(ctx, "pcm-capture-processor");

      worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        onChunk(event.data);
      };

      source.connect(worklet);
      worklet.connect(ctx.destination); // required for processing to run
      workletRef.current = worklet;

      setState("recording");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "麦克风访问失败";
      setError(msg);
      setState("error");
      throw err; // Re-throw so callers can detect failure
    }
  }, [onChunk]);

  const stop = useCallback(() => {
    workletRef.current?.port.postMessage("stop");
    workletRef.current?.disconnect();
    workletRef.current = null;

    if (contextRef.current?.state !== "closed") {
      void contextRef.current?.close();
    }
    contextRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    setState("idle");
  }, []);

  return { state, error, start, stop };
}
