import { ApiRequestError, apiGet, apiPostWithSignal } from "@/lib/api/client";
import type { TimelineGenerateData, TimelineGenerateRequest } from "@/lib/api/types";

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

export async function generateTimeline(
  payload: TimelineGenerateRequest,
  signal?: AbortSignal
): Promise<TimelineGenerateData> {
  const data = await apiPostWithSignal<TimelineGenerateData, TimelineGenerateRequest>("/generate/timeline", payload, signal);
  return validateTimelineData(data);
}

/** Fetch previously saved timeline from disk. Returns null if none saved. */
export async function getSavedTimeline(signal?: AbortSignal): Promise<TimelineGenerateData | null> {
  const data = await apiGet<TimelineGenerateData | null>("/generate/timeline/saved", signal);
  if (!data) return null;
  return validateTimelineData(data);
}
