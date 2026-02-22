import { ApiRequestError, parseEnvelope, normalizeApiError, getAuthHeaders } from "@/lib/api/client";
import type { ApiError, KnowledgeProcessData } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

function isApiError(value: unknown): value is ApiError {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.error_code === "string" &&
    typeof candidate.error_message === "string" &&
    typeof candidate.retryable === "boolean" &&
    typeof candidate.trace_id === "string"
  );
}

export async function processKnowledgeFile(username: string, file: File): Promise<KnowledgeProcessData> {
  const formData = new FormData();
  formData.append("username", username);
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/knowledge/process`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData
    });
  } catch {
    throw new ApiRequestError({
      code: "NETWORK_ERROR",
      message: "无法连接后端服务，请检查后端是否已启动",
      retryable: true
    });
  }

  const rawText = await response.text();
  let json: unknown = null;
  if (rawText) {
    try {
      json = JSON.parse(rawText);
    } catch {
      throw new ApiRequestError({
        code: "UNKNOWN_ERROR",
        message: `请求失败（HTTP ${response.status}）`,
        retryable: false
      });
    }
  }

  const envelope = parseEnvelope<KnowledgeProcessData>(json);
  if (envelope.status === "success" && envelope.data) {
    return envelope.data;
  }

  const first = envelope.errors[0];
  if (first && isApiError(first)) {
    throw new ApiRequestError(normalizeApiError(first));
  }

  throw new ApiRequestError({
    code: "UNKNOWN_ERROR",
    message: `请求失败（HTTP ${response.status}）`,
    retryable: false
  });
}
