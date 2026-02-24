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

export type TimelineGenerateRequest = {
  username: string;
  ratio?: number;
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

export type KnowledgeProcessData = {
  username: string;
  original_filename: string;
  stored_path: string;
  uploaded_at: string;
  trace_id: string;
  workflow_result: Record<string, unknown>;
};

export type TimelineEvent = {
  event_id: number;
  time: string;
  objective_summary: string;
  detailed_narrative: string;
};

export type TimelineGenerateData = {
  username: string;
  timeline: TimelineEvent[];
  event_count: number;
  generated_at: string;
  trace_id: string;
};

export type SessionCreateRequest = {
  username: string;
};

export type SessionCreateData = {
  session_id: string;
  thread_id: string;
  username: string;
  created_at: string;
};

export type SessionMessageRequest = {
  speaker: string;
  content: string;
  timestamp?: number;
};

export type SessionActionData = {
  session_id: string;
  thread_id: string;
  status: string;
  trace_id: string;
  details: Record<string, unknown>;
};

export type SessionCloseData = SessionActionData;

export type InterviewStreamConnected = {
  trace_id: string;
  session_id: string;
  connected_at: string;
  resumed: boolean;
};

export type InterviewStreamHeartbeat = {
  session_id: string;
  trace_id: string;
  at: string;
};

export type InterviewStreamStatus = {
  session_id: string;
  trace_id: string;
  status: string;
  speaker?: string;
  at?: string;
};

export type PendingEventDetail = {
  id: string;
  summary: string;
  is_priority: boolean;
  explored_length: number;
  explored_content: string;
};

export type EventSupplementItem = {
  event_summary: string;
  event_details: string;
};

export type InterviewStreamContext = {
  session_id: string;
  trace_id: string;
  partial?: "pending_events" | "supplements" | "anchors";
  background_meta?: Record<string, unknown>;
  pending_events?: {
    total: number;
    priority_count: number;
    unexplored_count: number;
    events: PendingEventDetail[];
  };
  event_supplements?: EventSupplementItem[];
  positive_triggers?: string[];
  sensitive_topics?: string[];
  at?: string;
};

export type InterviewStreamError = {
  session_id: string;
  error_code: string;
  error_message: string;
  retryable: boolean;
  trace_id: string;
  at?: string;
};

export type InterviewStreamCompleted = {
  session_id: string;
  trace_id: string;
  status: string;
  idle_seconds?: number;
  at?: string;
};

export type InterviewSseEventType = "connected" | "heartbeat" | "status" | "context" | "error" | "completed";

export type InterviewSsePayloadMap = {
  connected: InterviewStreamConnected;
  heartbeat: InterviewStreamHeartbeat;
  status: InterviewStreamStatus;
  context: InterviewStreamContext;
  error: InterviewStreamError;
  completed: InterviewStreamCompleted;
};

export type InterviewSseEnvelope<TType extends InterviewSseEventType = InterviewSseEventType> = {
  id: string;
  event: TType;
  data: InterviewSsePayloadMap[TType];
};

export type NormalizedApiError = {
  code: string;
  message: string;
  retryable: boolean;
  traceId?: string;
  details?: Record<string, unknown>;
};
