export type ApiError = {
  error_code: string;
  error_message: string;
  retryable: boolean;
  trace_id: string;
  error_details?: Record<string, unknown>;
};

export type ApiEnvelope<T> = {
  status: "success" | "failed";
  data: T | null;
  errors: ApiError[];
};

export type MemoirGenerateRequest = {
  username: string;
  target_length?: number;
  user_preferences?: string;
  auto_save?: boolean;
};

export type MemoirGenerateData = {
  username: string;
  memoir: string;
  length: number;
  generated_at: string;
  trace_id: string;
};

export type NormalizedApiError = {
  code: string;
  message: string;
  retryable: boolean;
  traceId?: string;
};
