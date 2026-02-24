"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square, Fingerprint, Check } from "lucide-react";
import { useAudioCapture } from "@/lib/hooks/use-audio-capture";
import { useIflytekAsr } from "@/lib/hooks/use-iflytek-asr";

/**
 * Debounce window (ms): consecutive segments from the same speaker
 * are merged into one before dispatching.
 */
const MERGE_DELAY = 2000;

const CALIBRATION_POEM = "白日依山尽，黄河入海流。\n欲穷千里目，更上一层楼。";

type Phase = "idle" | "countdown" | "calibrating" | "recording";

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
  const [countdown, setCountdown] = useState(3);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevSegmentCountRef = useRef(0);

  // Voiceprint: the rl number that belongs to the interviewee (user)
  const userRlRef = useRef<number | null>(null);
  const calibrationRlsRef = useRef<number[]>([]);

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

  const resolveRole = useCallback((rl: number): "interviewer" | "interviewee" => {
    if (userRlRef.current === null) return "interviewee"; // not calibrated yet
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

  // Process new segments: during calibrating → collect rl; during recording → merge & dispatch
  useEffect(() => {
    for (let i = prevSegmentCountRef.current; i < segments.length; i++) {
      const seg = segments[i];
      if (!seg.isFinal || !seg.text.trim()) continue;

      if (phase === "calibrating") {
        // Only collect genuine non-zero rawRl (actual speaker-switch markers from iFlytek)
        if (seg.rawRl > 0) {
          calibrationRlsRef.current.push(seg.rawRl);
        }
        continue;
      }

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
    // If already calibrated, skip calibration and go straight to recording
    if (userRlRef.current !== null) {
      reset();
      prevSegmentCountRef.current = 0;
      mergeBufferRef.current = null;
      if (mergeTimerRef.current) {
        clearTimeout(mergeTimerRef.current);
        mergeTimerRef.current = null;
      }
      await connect();
      try {
        await startCapture();
      } catch {
        disconnect();
        return;
      }
      setPhase("recording");
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((t) => t + 1), 1000);
      return;
    }

    // First time: start countdown → calibration → recording
    setCountdown(3);
    setPhase("countdown");

    let remaining = 3;
    countdownTimerRef.current = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        if (countdownTimerRef.current) {
          clearInterval(countdownTimerRef.current);
          countdownTimerRef.current = null;
        }
        // Start ASR + capture for calibration
        void (async () => {
          reset();
          prevSegmentCountRef.current = 0;
          calibrationRlsRef.current = [];
          await connect();
          try {
            await startCapture();
          } catch {
            disconnect();
            setPhase("idle");
            return;
          }
          setPhase("calibrating");
        })();
      } else {
        setCountdown(remaining);
      }
    }, 1000);
  }, [connect, disconnect, reset, startCapture]);

  const handleCalibrationDone = useCallback(() => {
    // Determine the user's rl from collected samples
    const rls = calibrationRlsRef.current;
    if (rls.length > 0) {
      // Most frequent rl during calibration = the user
      const counts = new Map<number, number>();
      for (const rl of rls) {
        counts.set(rl, (counts.get(rl) ?? 0) + 1);
      }
      let maxRl = rls[0];
      let maxCount = 0;
      for (const [rl, count] of counts) {
        if (count > maxCount) {
          maxRl = rl;
          maxCount = count;
        }
      }
      userRlRef.current = maxRl;
    } else {
      // Fallback: assume rl=2 is the user (rl=1 is usually first detected = interviewer)
      userRlRef.current = 1;
    }

    // Reset segments and transition to recording — ASR stays connected
    prevSegmentCountRef.current = segments.length; // skip calibration segments
    setPhase("recording");
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed((t) => t + 1), 1000);
  }, [segments.length]);

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

  const handleCancelCalibration = useCallback(() => {
    setPhase("idle");
    if (countdownTimerRef.current) {
      clearInterval(countdownTimerRef.current);
      countdownTimerRef.current = null;
    }
    stopCapture();
    disconnect();
  }, [disconnect, stopCapture]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current);
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
  const isCalibrated = userRlRef.current !== null;

  // --- Countdown UI ---
  if (phase === "countdown") {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <Fingerprint className="h-8 w-8 text-[#A2845E] animate-pulse" />
        <p className="text-sm text-slate-600">
          即将开始 <span className="font-medium text-[#A2845E]">{username}</span> 的声纹检测
        </p>
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#A2845E]/10 text-xl font-bold text-[#A2845E]">
          {countdown}
        </div>
        <button
          type="button"
          onClick={handleCancelCalibration}
          className="text-xs text-slate-400 hover:text-slate-600"
        >
          取消
        </button>
      </div>
    );
  }

  // --- Calibration UI ---
  if (phase === "calibrating") {
    return (
      <div className="flex flex-col items-center gap-3 py-2">
        <div className="flex items-center gap-2">
          <Fingerprint className="h-5 w-5 text-[#A2845E]" />
          <span className="text-xs font-medium text-[#A2845E] uppercase tracking-wider">声纹采集中</span>
          <div className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />
        </div>
        <div className="w-full rounded-lg border border-[#A2845E]/20 bg-[#F5EDE4] p-4 text-center">
          <p className="text-sm text-slate-500 mb-2">请朗读以下内容：</p>
          <p className="text-base leading-loose text-slate-800 whitespace-pre-line font-serif">
            {CALIBRATION_POEM}
          </p>
        </div>
        {/* Live partial text indicator */}
        {(partialText || segments.some((s) => s.isFinal)) && (
          <p className="text-xs text-slate-400">
            正在识别: {partialText || "..."}
          </p>
        )}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleCancelCalibration}
            className="rounded-lg px-4 py-1.5 text-xs text-slate-500 hover:bg-slate-100 transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleCalibrationDone}
            className="flex items-center gap-1.5 rounded-lg bg-[#A2845E] px-4 py-1.5 text-xs font-medium text-white hover:bg-[#8B7050] transition-colors shadow-sm"
          >
            <Check className="h-3.5 w-3.5" />
            读完了
          </button>
        </div>
        {errorMsg && (
          <p className="text-center text-xs text-rose-500">{errorMsg}</p>
        )}
      </div>
    );
  }

  // --- Recording / Idle UI ---
  return (
    <div className="flex flex-col gap-3">
      {/* Live transcription area (only during recording) */}
      {phase === "recording" && (
        <div className="max-h-[140px] min-h-[60px] overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs leading-relaxed text-slate-600">
          {process.env.NODE_ENV === "development" && (
            <div className="mb-1 text-[10px] text-slate-400 border-b border-slate-200 pb-1">
              userRl={userRlRef.current ?? "null"} |
              segments(post-cal): {segments.filter((s) => s.isFinal).length - (prevSegmentCountRef.current)}
            </div>
          )}
          {segments
            .filter((s) => s.isFinal)
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

        {/* Calibration status indicator */}
        {phase === "idle" && (
          <div className="flex items-center gap-1">
            <Fingerprint className={`h-3.5 w-3.5 ${isCalibrated ? "text-emerald-500" : "text-slate-300"}`} />
            <span className={`text-[10px] ${isCalibrated ? "text-emerald-500" : "text-slate-400"}`}>
              {isCalibrated ? "已校准" : "首次需校准"}
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
