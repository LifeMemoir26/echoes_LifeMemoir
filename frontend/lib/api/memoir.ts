import { ApiRequestError, apiPost } from "@/lib/api/client";
import type { MemoirGenerateData, MemoirGenerateRequest } from "@/lib/api/types";

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

export async function generateMemoir(payload: MemoirGenerateRequest): Promise<MemoirGenerateData> {
  const data = await apiPost<MemoirGenerateData, MemoirGenerateRequest>("/generate/memoir", {
    username: payload.username,
    target_length: payload.target_length ?? 2000,
    user_preferences: payload.user_preferences,
    auto_save: payload.auto_save ?? true
  });

  return validateMemoirData(data);
}
