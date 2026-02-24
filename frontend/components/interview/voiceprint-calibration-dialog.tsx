"use client";

import type { CalibrationStep } from "@/lib/hooks/use-voiceprint-calibration";

type Props = {
  step: CalibrationStep;
  username: string;
  onNext: () => void;
  onCancel: () => void;
};

const stepConfig: Record<
  Exclude<CalibrationStep, "idle" | "done">,
  { title: string; instruction: string; actionLabel: string }
> = {
  interviewer_speaking: {
    title: "采访者声纹采集",
    instruction: "请采访者对着麦克风说几句话（约 5 秒），完成后点击下一步。",
    actionLabel: "下一步：受访者录音",
  },
  interviewee_speaking: {
    title: "受访者声纹采集",
    instruction: "请受访者对着麦克风说几句话（约 5 秒），完成后点击完成校准。",
    actionLabel: "完成校准",
  },
};

export function VoiceprintCalibrationDialog({ step, username, onNext, onCancel }: Props) {
  if (step === "idle" || step === "done") return null;

  const config = stepConfig[step];
  const stepNumber = step === "interviewer_speaking" ? 1 : 2;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-[380px] rounded-2xl border border-black/[0.06] bg-white p-6 shadow-lg">
        {/* Header */}
        <div className="mb-4 text-center">
          <p className="text-xs uppercase tracking-[0.16em] text-[#A2845E] mb-1">
            声纹校准 · 步骤 {stepNumber}/2
          </p>
          <h3 className="text-base font-medium text-slate-800">{config.title}</h3>
        </div>

        {/* Recording indicator */}
        <div className="mb-4 flex flex-col items-center gap-3">
          <div className="relative flex h-16 w-16 items-center justify-center">
            {/* Pulse animation */}
            <div className="absolute inset-0 animate-ping rounded-full bg-[#A2845E]/20" />
            <div className="relative h-12 w-12 rounded-full bg-[#A2845E] flex items-center justify-center">
              <div className="h-4 w-4 rounded-full bg-white animate-pulse" />
            </div>
          </div>
          <p className="text-sm text-slate-600 text-center px-4">
            {step === "interviewer_speaking"
              ? config.instruction
              : config.instruction.replace("受访者", username || "受访者")}
          </p>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onNext}
            className="flex-1 rounded-lg bg-[#A2845E] px-3 py-2 text-sm font-medium text-white hover:bg-[#8B7050] transition-colors"
          >
            {config.actionLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
