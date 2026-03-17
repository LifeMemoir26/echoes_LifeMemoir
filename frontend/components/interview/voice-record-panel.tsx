"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square, Fingerprint } from "lucide-react";
import { useAudioCapture } from "@/lib/hooks/use-audio-capture";
import { useIflytekAsr } from "@/lib/hooks/use-iflytek-asr";
import { loadVoiceprint, hasVoiceprint as checkVoiceprint } from "@/lib/voiceprint-db";

/**
 * Debounce window (ms): consecutive segments from the same speaker
 * are merged into one before dispatching.
 */
const MERGE_DELAY = 3000;

/**
 * Inter-chunk pacing (ms) when replaying voiceprint audio to iFlytek.
 *
 * iFlytek official SDK uses 40 ms (real-time rate, 1280 B per 40 ms).
 * Docs warn "发送过快可能导致引擎出错", so keep the priming replay at
 * the same pacing as live audio chunks.
 */
const CHUNK_PACE_MS = 40;

/**
 * After sending all voiceprint chunks, we poll prevSegmentCountRef.
 * Once no new segments arrive for SETTLE_MS, we consider priming done.
 */
const SETTLE_MS = 1500;
/** Minimum total wait before we can finish priming (ms). */
const MIN_PRIME_WAIT = 2000;
/** Safety cap so we never hang forever (ms). */
const MAX_PRIME_WAIT = 10_000;

/**
 * The voiceprint poem text (stripped of punctuation) used as a
 * content-based safety filter. Even if a late voiceprint segment
 * slips past the index boundary, we catch it by text matching.
 */
const VOICEPRINT_POEM_CLEAN = "白日依山尽黄河入海流";

function isVoiceprintText(text: string): boolean {
  const clean = text.replace(/[，。、！？,.\s]/g, "");
  if (clean.length < 2) return false;
  return VOICEPRINT_POEM_CLEAN.includes(clean) || clean.includes(VOICEPRINT_POEM_CLEAN);
}

type Phase = "idle" | "priming" | "recording";

type Props = {
  username: string;
  /** Called with merged text when a speaker's turn is finalized */
  onSegment: (segment: { speaker: string; content: string }) => void;
  disabled?: boolean;
};

export function VoiceRecordPanel({
  username,
  onSegment,
  disabled,
}: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [hasVp, setHasVp] = useState<boolean | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevSegmentCountRef = useRef(0);

  /**
   * The segment index at which live recording begins.
   * Segments before this index are voiceprint priming data
   * and should NOT appear in the live transcription area.
   */
  const recordingStartIdxRef = useRef(0);

  /** Interviewee's rl number — always 1 after voiceprint priming. */
  const userRlRef = useRef<number>(1);

  // Merge buffer
  const mergeBufferRef = useRef<{ speaker: string; texts: string[] } | null>(null);
  const mergeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { status: asrStatus, error: asrError, segments, partialText, connect, sendAudio, disconnect, reset } =
    useIflytekAsr();

  const onChunk = useCallback(
    (chunk: ArrayBuffer) => {
      sendAudio(chunk);
    },
    [sendAudio]
  );

  const { error: captureError, start: startCapture, stop: stopCapture } =
    useAudioCapture(onChunk);

  // Stable ref for onSegment
  const onSegmentRef = useRef(onSegment);
  onSegmentRef.current = onSegment;

  // Check IndexedDB for saved voiceprint on mount / username change
  useEffect(() => {
    if (!username) return;
    let cancelled = false;
    checkVoiceprint(username).then((exists) => {
      if (!cancelled) setHasVp(exists);
    });
    return () => { cancelled = true; };
  }, [username]);

  const resolveRole = useCallback((rl: number): "interviewer" | "interviewee" => {
    return rl === userRlRef.current ? "interviewee" : "interviewer";
  }, []);

  const flushMergeBuffer = useCallback(() => {
    if (mergeTimerRef.current) {
      clearTimeout(mergeTimerRef.current);
      mergeTimerRef.current = null;
    }
    const buf = mergeBufferRef.current;
    if (buf && buf.texts.length > 0) {
      onSegmentRef.current({
        speaker: buf.speaker,
        content: buf.texts.join(""),
      });
    }
    mergeBufferRef.current = null;
  }, []);

  // Process new segments: skip anything before the recording boundary,
  // then merge & dispatch during recording phase.
  useEffect(() => {
    for (let i = prevSegmentCountRef.current; i < segments.length; i++) {
      const seg = segments[i];
      if (!seg.isFinal || !seg.text.trim()) continue;

      // Hard boundary: always skip voiceprint priming segments,
      // even if a late one arrives after phase switched to "recording".
      if (i < recordingStartIdxRef.current) continue;

      // Safety net: content-based filter catches any voiceprint segment
      // that slips past the index boundary due to processing delays.
      if (isVoiceprintText(seg.text)) continue;

      if (phase === "recording") {
        const role = resolveRole(seg.roleNumber);
        const speaker = role === "interviewer" ? "interviewer" : (username || "interviewee");
        const text = seg.text.trim();

        const buf = mergeBufferRef.current;
        if (buf && buf.speaker !== speaker) {
          flushMergeBuffer();
        }

        if (!mergeBufferRef.current) {
          mergeBufferRef.current = { speaker, texts: [] };
        }
        mergeBufferRef.current.texts.push(text);

        if (mergeTimerRef.current) clearTimeout(mergeTimerRef.current);
        mergeTimerRef.current = setTimeout(flushMergeBuffer, MERGE_DELAY);
      }
    }
    prevSegmentCountRef.current = segments.length;
  }, [segments, phase, resolveRole, username, flushMergeBuffer]);

  // --- Actions ---

  const handleStart = useCallback(async () => {
    reset();
    prevSegmentCountRef.current = 0;
    // Block ALL segments until priming completes
    recordingStartIdxRef.current = Infinity;
    mergeBufferRef.current = null;
    if (mergeTimerRef.current) {
      clearTimeout(mergeTimerRef.current);
      mergeTimerRef.current = null;
    }

    await connect();

    // Load voiceprint from IndexedDB and replay it to register
    // the interviewee as rl=1 (first detected speaker).
    const chunks = await loadVoiceprint(username);

    if (chunks && chunks.length > 0) {
      setPhase("priming");

      // Send chunks at the same 40 ms cadence recommended by iFlytek.
      // Faster replay can hurt engine stability and diarization quality.
      for (const chunk of chunks) {
        sendAudio(chunk);
        await new Promise<void>((r) => setTimeout(r, CHUNK_PACE_MS));
      }

      // IMPORTANT: Do NOT send {end: true} here!
      // The iFlytek end signal terminates the WebSocket session
      // permanently — the speaker model would be lost.
      // Instead, keep the connection open and wait for the engine
      // to finish processing the voiceprint audio.

      // Poll prevSegmentCountRef: once no new segments arrive for
      // SETTLE_MS (and we've waited at least MIN_PRIME_WAIT), the
      // engine has finished processing the voiceprint.
      await new Promise<void>((resolve) => {
        let lastCount = prevSegmentCountRef.current;
        let stableMs = 0;
        let totalMs = 0;
        const POLL = 200;

        const poll = setInterval(() => {
          totalMs += POLL;
          const now = prevSegmentCountRef.current;
          if (now === lastCount) {
            stableMs += POLL;
          } else {
            lastCount = now;
            stableMs = 0;
          }
          if ((totalMs >= MIN_PRIME_WAIT && stableMs >= SETTLE_MS) || totalMs >= MAX_PRIME_WAIT) {
            clearInterval(poll);
            resolve();
          }
        }, POLL);
      });
    }

    // Lock the recording boundary — all segments up to this point
    // are voiceprint data and will be filtered out.
    userRlRef.current = 1;
    recordingStartIdxRef.current = prevSegmentCountRef.current;

    // Start live microphone capture on the SAME WebSocket connection
    // so iFlytek's speaker model from the voiceprint is preserved.
    try {
      await startCapture();
    } catch {
      disconnect();
      setPhase("idle");
      return;
    }

    setPhase("recording");
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed((t) => t + 1), 1000);
  }, [connect, disconnect, reset, startCapture, sendAudio, username]);

  const handleStop = useCallback(() => {
    setPhase("idle");
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    stopCapture();
    disconnect();
    flushMergeBuffer();
  }, [disconnect, stopCapture, flushMergeBuffer]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (mergeTimerRef.current) clearTimeout(mergeTimerRef.current);
      stopCapture();
      disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const errorMsg = asrError || captureError;

  // --- Priming UI ---
  if (phase === "priming") {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <Fingerprint className="h-6 w-6 text-[#A2845E] animate-pulse" />
        <span className="text-xs text-[#A2845E]">声纹初始化中…</span>
      </div>
    );
  }

  // --- Recording / Idle UI ---
  return (
    <div className="flex flex-col gap-3">
      {/* Live transcription area (only during recording) */}
      {phase === "recording" && (
        <div className="max-h-[140px] min-h-[60px] overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs leading-relaxed text-slate-600">
          {segments
            .slice(recordingStartIdxRef.current)
            .filter((s) => !isVoiceprintText(s.text))
            .map((s, i) => {
              const role = resolveRole(s.roleNumber);
              const label = role === "interviewer" ? "采访者" : (username || "受访者");
              return (
                <span key={i}>
                  <span className={role === "interviewer" ? "text-slate-500 font-medium" : "text-[#A2845E] font-medium"}>
                    [{label}]
                  </span>
                  {s.text}
                </span>
              );
            })}
          {partialText && (
            <span className="text-slate-400 italic">{partialText}</span>
          )}
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center justify-center gap-3">
        {phase === "recording" && (
          <span className="text-xs text-slate-500 tabular-nums">{formatTime(elapsed)}</span>
        )}

        <button
          type="button"
          onClick={phase === "recording" ? handleStop : () => void handleStart()}
          disabled={disabled || (asrStatus === "connecting")}
          className={`flex h-14 w-14 items-center justify-center rounded-full transition-all ${
            phase === "recording"
              ? "bg-rose-500 hover:bg-rose-600 text-white shadow-lg shadow-rose-200"
              : "bg-[#A2845E] hover:bg-[#8B7050] text-white shadow-lg shadow-[#A2845E]/20"
          } disabled:opacity-50`}
          aria-label={phase === "recording" ? "停止录音" : "开始录音"}
        >
          {phase === "recording" ? (
            <Square className="h-5 w-5" />
          ) : (
            <Mic className="h-6 w-6" />
          )}
        </button>

        {phase === "recording" && (
          <div className="flex items-center gap-1">
            <div className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />
            <span className="text-xs text-rose-500">录音中</span>
          </div>
        )}

        {/* Voiceprint status indicator */}
        {phase === "idle" && (
          <div className="flex items-center gap-1">
            <Fingerprint className={`h-3.5 w-3.5 ${hasVp ? "text-emerald-500" : "text-slate-300"}`} />
            <span className={`text-[10px] ${hasVp ? "text-emerald-500" : "text-slate-400"}`}>
              {hasVp ? "声纹就绪" : `请先在主页采集${username}声纹`}
            </span>
          </div>
        )}
      </div>

      {errorMsg && (
        <p className="text-center text-xs text-rose-500">{errorMsg}</p>
      )}
    </div>
  );
}
