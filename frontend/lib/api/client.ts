import type { ApiEnvelope, ApiError, InterviewStreamError, NormalizedApiError } from "@/lib/api/types";

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

export function isApiError(value: unknown): value is ApiError {
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
    traceId: error.trace_id,
    details: error.error_details
  };
}

export function normalizeInterviewSseError(error: InterviewStreamError): NormalizedApiError {
  return {
    code: error.error_code,
    message: error.error_message,
    retryable: error.retryable,
    traceId: error.trace_id
  };
}

export function normalizeUnknownError(error: unknown, fallbackMessage: string): NormalizedApiError {
  if (error instanceof ApiRequestError) {
    return error.normalized;
  }

  if (error instanceof Error) {
    if (/failed to fetch/i.test(error.message)) {
      return {
        code: "NETWORK_ERROR",
        message: "无法连接后端服务，请检查后端是否已启动",
        retryable: true
      };
    }

    return {
      code: "UNKNOWN_ERROR",
      message: error.message || fallbackMessage,
      retryable: false
    };
  }

  return {
    code: "UNKNOWN_ERROR",
    message: fallbackMessage,
    retryable: false
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

async function parseResponseToEnvelope<TData>(response: Response): Promise<ApiEnvelope<TData>> {
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

  // FastAPI wraps HTTPException body as {"detail": {...}} — unwrap it so the
  // standard envelope parser works for both success and error responses.
  const unwrapped =
    json &&
    typeof json === "object" &&
    "detail" in (json as Record<string, unknown>)
      ? (json as Record<string, unknown>).detail
      : json;

  try {
    return parseEnvelope<TData>(unwrapped);
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
}

function throwFirstApiErrorOrContract<TData>(envelope: ApiEnvelope<TData>): never {
  const first = envelope.errors[0];
  if (first) {
    throw new ApiRequestError(normalizeApiError(first));
  }

  throw new ContractError("Failed response without errors");
}

async function requestJson<TData>(input: RequestInfo | URL, init: RequestInit): Promise<TData> {
  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      credentials: init.credentials ?? "include"
    });
  } catch (error) {
    const errorName =
      error && typeof error === "object" && "name" in error ? String((error as { name?: unknown }).name) : "";
    if (errorName === "AbortError") {
      throw new ApiRequestError({
        code: "REQUEST_ABORTED",
        message: "请求已取消",
        retryable: true
      });
    }

    throw new ApiRequestError({
      code: "NETWORK_ERROR",
      message: "无法连接后端服务，请检查后端是否已启动",
      retryable: true
    });
  }

  const envelope = await parseResponseToEnvelope<TData>(response);
  if (envelope.status === "success") {
    return envelope.data as TData;
  }

  throwFirstApiErrorOrContract(envelope);
}

export async function apiPost<TData, TRequest>(path: string, body: TRequest): Promise<TData> {
  return apiPostWithSignal<TData, TRequest>(path, body);
}

export async function apiPostWithSignal<TData, TRequest>(
  path: string,
  body: TRequest,
  signal?: AbortSignal
): Promise<TData> {
  return requestJson<TData>(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal
  });
}

export async function apiDelete<TData>(path: string): Promise<TData> {
  return requestJson<TData>(`${API_BASE_URL}${path}`, {
    method: "DELETE"
  });
}

export async function apiPatch<TData>(path: string): Promise<TData> {
  return requestJson<TData>(`${API_BASE_URL}${path}`, {
    method: "PATCH"
  });
}

export async function apiGet<TData>(path: string, signal?: AbortSignal): Promise<TData> {
  return requestJson<TData>(`${API_BASE_URL}${path}`, {
    method: "GET",
    signal
  });
}

export async function apiPostFormData<TData>(path: string, formData: FormData): Promise<TData> {
  return requestJson<TData>(`${API_BASE_URL}${path}`, {
    method: "POST",
    body: formData,
  });
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}
