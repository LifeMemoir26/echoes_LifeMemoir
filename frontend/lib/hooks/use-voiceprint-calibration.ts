"use client";

import { useCallback, useRef, useState } from "react";

export type CalibrationStep = "idle" | "interviewer_speaking" | "interviewee_speaking" | "done";

/**
 * Maps iFlytek rl (role number) → "interviewer" | "interviewee"
 */
export type VoiceprintMap = Record<number, "interviewer" | "interviewee">;

/**
 * In-memory voiceprint calibration hook.
 *
 * During calibration, each person speaks for a few seconds. We observe
 * which iFlytek `rl` numbers appear and build a mapping.
 * Data is stored in component state only — lost on page refresh.
 */
export function useVoiceprintCalibration() {
  const [step, setStep] = useState<CalibrationStep>("idle");
  const [voiceprintMap, setVoiceprintMap] = useState<VoiceprintMap | null>(null);

  // Collect rl numbers observed during each calibration phase
  const interviewerRolesRef = useRef<number[]>([]);
  const intervieweeRolesRef = useRef<number[]>([]);

  const startCalibration = useCallback(() => {
    interviewerRolesRef.current = [];
    intervieweeRolesRef.current = [];
    setVoiceprintMap(null);
    setStep("interviewer_speaking");
  }, []);

  /**
   * Feed observed rl numbers from ASR segments during calibration.
   * Call this for each finalized ASR segment.
   */
  const feedRole = useCallback((roleNumber: number) => {
    if (roleNumber <= 0) return;

    if (step === "interviewer_speaking") {
      interviewerRolesRef.current.push(roleNumber);
    } else if (step === "interviewee_speaking") {
      intervieweeRolesRef.current.push(roleNumber);
    }
  }, [step]);

  /**
   * Move to the next calibration phase.
   */
  const nextStep = useCallback(() => {
    if (step === "interviewer_speaking") {
      setStep("interviewee_speaking");
    } else if (step === "interviewee_speaking") {
      // Analyze results and build the mapping
      const interviewerMode = getMostFrequent(interviewerRolesRef.current);
      const intervieweeMode = getMostFrequent(intervieweeRolesRef.current);

      if (interviewerMode !== null && intervieweeMode !== null && interviewerMode !== intervieweeMode) {
        setVoiceprintMap({
          [interviewerMode]: "interviewer",
          [intervieweeMode]: "interviewee",
        });
      } else if (interviewerMode !== null) {
        // Fallback: if we only detected one speaker, assign the other
        const otherRole = interviewerMode === 1 ? 2 : 1;
        setVoiceprintMap({
          [interviewerMode]: "interviewer",
          [otherRole]: "interviewee",
        });
      } else {
        // Default mapping
        setVoiceprintMap({ 1: "interviewer", 2: "interviewee" });
      }

      setStep("done");
    }
  }, [step]);

  const resetCalibration = useCallback(() => {
    setStep("idle");
    setVoiceprintMap(null);
    interviewerRolesRef.current = [];
    intervieweeRolesRef.current = [];
  }, []);

  /**
   * Resolve an iFlytek rl number to a speaker role using the calibration map.
   */
  const resolveRole = useCallback(
    (roleNumber: number): "interviewer" | "interviewee" => {
      if (!voiceprintMap) return "interviewee"; // uncalibrated fallback
      return voiceprintMap[roleNumber] ?? "interviewee";
    },
    [voiceprintMap]
  );

  return {
    step,
    voiceprintMap,
    isCalibrated: voiceprintMap !== null,
    startCalibration,
    feedRole,
    nextStep,
    resetCalibration,
    resolveRole,
  };
}

function getMostFrequent(arr: number[]): number | null {
  if (arr.length === 0) return null;
  const counts = new Map<number, number>();
  for (const val of arr) {
    counts.set(val, (counts.get(val) ?? 0) + 1);
  }
  let maxCount = 0;
  let maxVal: number | null = null;
  for (const [val, count] of counts) {
    if (count > maxCount) {
      maxCount = count;
      maxVal = val;
    }
  }
  return maxVal;
}
