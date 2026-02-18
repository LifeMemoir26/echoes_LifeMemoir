import { apiPost } from "@/lib/api/client";
import type { MemoirGenerateData, MemoirGenerateRequest } from "@/lib/api/types";

export async function generateMemoir(payload: MemoirGenerateRequest): Promise<MemoirGenerateData> {
  return apiPost<MemoirGenerateData, MemoirGenerateRequest>("/generate/memoir", {
    username: payload.username,
    target_length: payload.target_length ?? 2000,
    user_preferences: payload.user_preferences,
    auto_save: payload.auto_save ?? true
  });
}
