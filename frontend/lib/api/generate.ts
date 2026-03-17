import { ApiRequestError, apiGet, apiPost, apiPostWithSignal } from "@/lib/api/client";
import type {
  GenerationStatusData,
  MemoirGenerateData,
  MemoirGenerateRequest,
  TimelineGenerateData,
  TimelineGenerateRequest,
} from "@/lib/api/types";

function validateMemoirData(data: MemoirGenerateData): MemoirGenerateData {
  if (
    typeof data.username !== "string" ||
    typeof data.memoir !== "string" ||
    typeof data.length !== "number" ||
    typeof data.generated_at !== "string" ||
    typeof data.trace_id !== "string"
  ) {
    throw new ApiRequestError({
      code: "CONTRACT_ERROR",
      message: "回忆录响应结构不符合接口契约",
      retryable: false
    });
  }

  return data;
}

function validateTimelineData(data: TimelineGenerateData): TimelineGenerateData {
  if (
    typeof data.username !== "string" ||
    !Array.isArray(data.timeline) ||
    typeof data.event_count !== "number" ||
    typeof data.generated_at !== "string" ||
    typeof data.trace_id !== "string"
  ) {
    throw new ApiRequestError({
      code: "CONTRACT_ERROR",
      message: "时间线响应结构不符合接口契约",
      retryable: false
    });
  }
  return data;
}

function validateGenerationStatusData(data: GenerationStatusData): GenerationStatusData {
  if (
    typeof data.username !== "string" ||
    typeof data.timeline_active !== "boolean" ||
    typeof data.memoir_active !== "boolean" ||
    typeof data.checked_at !== "string"
  ) {
    throw new ApiRequestError({
      code: "CONTRACT_ERROR",
      message: "生成状态响应结构不符合接口契约",
      retryable: false
    });
  }
  return data;
}

export async function generateMemoir(payload: MemoirGenerateRequest): Promise<MemoirGenerateData> {
  const data = await apiPost<MemoirGenerateData, MemoirGenerateRequest>("/generate/memoir", {
    username: payload.username,
    target_length: payload.target_length ?? 2000,
    user_preferences: payload.user_preferences,
    auto_save: payload.auto_save ?? true
  });

  return validateMemoirData(data);
}

export async function getSavedMemoir(signal?: AbortSignal): Promise<MemoirGenerateData | null> {
  const data = await apiGet<MemoirGenerateData | null>("/generate/memoir/saved", signal);
  if (!data) return null;
  return validateMemoirData(data);
}

export async function getGenerationStatus(signal?: AbortSignal): Promise<GenerationStatusData> {
  const data = await apiGet<GenerationStatusData>("/generate/status", signal);
  return validateGenerationStatusData(data);
}

export async function generateTimeline(
  payload: TimelineGenerateRequest,
  signal?: AbortSignal
): Promise<TimelineGenerateData> {
  const data = await apiPostWithSignal<TimelineGenerateData, TimelineGenerateRequest>("/generate/timeline", payload, signal);
  return validateTimelineData(data);
}

export async function getSavedTimeline(signal?: AbortSignal): Promise<TimelineGenerateData | null> {
  const data = await apiGet<TimelineGenerateData | null>("/generate/timeline/saved", signal);
  if (!data) return null;
  return validateTimelineData(data);
}
