"use client";

import { useCallback, useRef, useState } from "react";
import { Fingerprint, Mic, Square, RotateCcw, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAudioCapture } from "@/lib/hooks/use-audio-capture";
import { saveVoiceprint } from "@/lib/voiceprint-db";

const CALIBRATION_POEM = "白日依山尽，黄河入海流。";
const AUTO_STOP_SECONDS = 5;

type Phase = "ready" | "recording" | "recorded" | "saving";

interface Props {
  open: boolean;
  username: string;
  onDone: () => void;
  onClose: () => void;
}

export function VoiceprintCollector({ open, username, onDone, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>("ready");
  const [remaining, setRemaining] = useState(AUTO_STOP_SECONDS);
  const [error, setError] = useState<string | null>(null);
  const chunksRef = useRef<ArrayBuffer[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoStopRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onChunk = useCallback((chunk: ArrayBuffer) => {
    chunksRef.current.push(chunk);
  }, []);

  const { error: captureError, start: startCapture, stop: stopCapture } =
    useAudioCapture(onChunk);

  const handleStart = useCallback(async () => {
    setError(null);
    chunksRef.current = [];
    try {
      await startCapture();
    } catch {
      return; // useAudioCapture already sets its error
    }
    setPhase("recording");
    setRemaining(AUTO_STOP_SECONDS);

    // Countdown timer (1 Hz)
    timerRef.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          // Auto-stop when countdown reaches 0
          if (timerRef.current) clearInterval(timerRef.current);
          if (autoStopRef.current) clearTimeout(autoStopRef.current);
          stopCapture();
          setPhase("recorded");
          return 0;
        }
        return r - 1;
      });
    }, 1000);

    // Safety auto-stop timeout (in case setRemaining doesn't trigger)
    autoStopRef.current = setTimeout(() => {
      if (timerRef.current) clearInterval(timerRef.current);
      stopCapture();
      setPhase("recorded");
    }, AUTO_STOP_SECONDS * 1000);
  }, [startCapture, stopCapture]);

  const handleStop = useCallback(() => {
    stopCapture();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (autoStopRef.current) {
      clearTimeout(autoStopRef.current);
      autoStopRef.current = null;
    }
    setPhase("recorded");
  }, [stopCapture]);

  const handleReRecord = useCallback(() => {
    chunksRef.current = [];
    setRemaining(AUTO_STOP_SECONDS);
    setPhase("ready");
  }, []);

  const handleSave = useCallback(async () => {
    if (chunksRef.current.length === 0) {
      setError("未检测到录音数据");
      return;
    }
    setPhase("saving");
    setError(null);
    try {
      await saveVoiceprint(username, chunksRef.current);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
      setPhase("recorded");
    }
  }, [username, onDone]);

  const handleClose = useCallback(() => {
    // Clean up if recording is in progress
    if (phase === "recording") {
      stopCapture();
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      if (autoStopRef.current) {
        clearTimeout(autoStopRef.current);
        autoStopRef.current = null;
      }
    }
    chunksRef.current = [];
    setPhase("ready");
    setRemaining(AUTO_STOP_SECONDS);
    setError(null);
    onClose();
  }, [phase, stopCapture, onClose]);

  if (!open) return null;

  const displayError = error || captureError;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-black/[0.06] bg-white p-6 shadow-xl">
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Fingerprint className="h-5 w-5 text-[#A2845E]" />
            <h2 className="font-semibold text-slate-900">声纹采集</h2>
          </div>
          <button
            onClick={handleClose}
            className="cursor-pointer rounded-lg p-1 text-slate-400 hover:text-slate-600"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Instructions */}
        <p className="mb-3 text-sm text-slate-500">
          请朗读以下诗句，{AUTO_STOP_SECONDS} 秒后自动结束录制。
        </p>
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-xs text-amber-800">
            ⚠️ 录制期间请保持安静，不可有除 <span className="font-medium">{username}</span> 之外的声音
          </p>
        </div>

        {/* Poem card */}
        <div className="mb-5 rounded-xl border border-[#A2845E]/20 bg-[#F5EDE4] p-4 text-center">
          <p className="text-base leading-loose text-slate-800 whitespace-pre-line font-serif">
            {CALIBRATION_POEM}
          </p>
        </div>

        {/* Recording countdown */}
        {phase === "recording" && (
          <div className="mb-4 flex items-center justify-center gap-3">
            <div className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />
            <span className="text-sm text-rose-500">录音中</span>
            <span className="text-sm tabular-nums text-slate-500">{remaining}s</span>
          </div>
        )}

        {phase === "recorded" && (
          <div className="mb-4 flex items-center justify-center gap-2">
            <Check className="h-4 w-4 text-emerald-500" />
            <span className="text-sm text-emerald-600">录制完成</span>
          </div>
        )}

        {phase === "saving" && (
          <div className="mb-4 text-center text-sm text-slate-500">保存中…</div>
        )}

        {displayError && (
          <p className="mb-4 text-center text-xs text-rose-500">{displayError}</p>
        )}

        {/* Actions */}
        <div className="flex items-center justify-center gap-3">
          {phase === "ready" && (
            <Button
              onClick={() => void handleStart()}
              className="gap-2"
            >
              <Mic className="h-4 w-4" />
              开始录制
            </Button>
          )}

          {phase === "recording" && (
            <button
              type="button"
              onClick={handleStop}
              className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-500 text-white shadow-lg shadow-rose-200 transition-all hover:bg-rose-600"
              aria-label="停止录音"
            >
              <Square className="h-5 w-5" />
            </button>
          )}

          {phase === "recorded" && (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleReRecord}
                className="gap-1.5"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                重新录制
              </Button>
              <Button
                size="sm"
                onClick={() => void handleSave()}
                className="gap-1.5"
              >
                <Check className="h-3.5 w-3.5" />
                保存声纹
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
