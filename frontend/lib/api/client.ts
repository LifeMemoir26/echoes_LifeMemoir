import type { ApiEnvelope, ApiError, NormalizedApiError } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

export class ContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractError";
  }
}

export class ApiRequestError extends Error {
  public readonly normalized: NormalizedApiError;

  constructor(error: NormalizedApiError) {
    super(error.message);
    this.name = "ApiRequestError";
    this.normalized = error;
  }
}

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

export function normalizeApiError(error: ApiError): NormalizedApiError {
  return {
    code: error.error_code,
    message: error.error_message,
    retryable: error.retryable,
    traceId: error.trace_id
  };
}

export function parseEnvelope<T>(payload: unknown): ApiEnvelope<T> {
  if (!payload || typeof payload !== "object") {
    throw new ContractError("API response is not an object");
  }

  const obj = payload as Record<string, unknown>;
  if (obj.status !== "success" && obj.status !== "failed") {
    throw new ContractError("API response status is invalid");
  }

  if (!Array.isArray(obj.errors) || !obj.errors.every(isApiError)) {
    throw new ContractError("API response errors contract mismatch");
  }

  return {
    status: obj.status,
    data: (obj.data as T | null) ?? null,
    errors: obj.errors
  };
}

export async function apiPost<TData, TRequest>(path: string, body: TRequest): Promise<TData> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

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

  let envelope: ApiEnvelope<TData>;
  try {
    envelope = parseEnvelope<TData>(json);
  } catch (error) {
    if (error instanceof ContractError) {
      throw new ApiRequestError({
        code: "CONTRACT_ERROR",
        message: "响应结构不符合接口契约",
        retryable: false
      });
    }
    throw error;
  }
  if (envelope.status === "success" && envelope.data) {
    return envelope.data;
  }

  const first = envelope.errors[0];
  if (first) {
    throw new ApiRequestError(normalizeApiError(first));
  }

  throw new ContractError("Failed response without errors");
}
