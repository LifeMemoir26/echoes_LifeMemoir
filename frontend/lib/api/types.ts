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

export type GenerationStatusData = {
  username: string;
  timeline_active: boolean;
  memoir_active: boolean;
  checked_at: string;
};

export type SessionCreateRequest = {
  username: string;
};

export type RegisterRequest = {
  username: string;
  password: string;
};

export type RegisterData = {
  username: string;
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type LoginData = {
  access_token: string;
  token_type: string;
  username: string;
};

export type AuthSessionData = {
  username: string;
};

export type LogoutData = {
  logged_out: boolean;
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

export type KnowledgeProcessData = {
  username: string;
  original_filename: string;
  stored_path: string;
  uploaded_at: string;
  trace_id: string;
  workflow_result: Record<string, unknown>;
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

export type SseEventPayload = {
  event: string;
  session_id: string;
  trace_id: string;
  payload: Record<string, unknown>;
};

export type NormalizedApiError = {
  code: string;
  message: string;
  retryable: boolean;
  traceId?: string;
  details?: Record<string, unknown>;
};

// ── Knowledge domain types ──────────────────────────────────

export type RecordItem = {
  chunk_id: number;
  chunk_source: string | null;
  preview: string;
  total_chars: number;
  chunk_index: number;
  created_at: string;
  is_structured: boolean;
};

export type RecordsListData = {
  records: RecordItem[];
};

export type EventItem = {
  id: number;
  year: string;
  time_detail: string | null;
  event_summary: string;
  event_details: string | null;
  is_merged: boolean;
  created_at: string;
  life_stage: string | null;
  event_category: string[];
  confidence: "high" | "medium" | "low" | null;
  source_material_id: string | null;
};

export type EventsListData = {
  events: EventItem[];
};

export type ProfileData = {
  personality: string;
  worldview: string;
};

export type MaterialItem = {
  id: string;
  filename: string;
  display_name: string;
  material_type: string;
  material_context: string;
  file_path: string | null;
  file_size: number;
  status: "pending" | "processing" | "done" | "failed";
  events_count: number;
  chunks_count: number;
  uploaded_at: string;
  processed_at: string | null;
};

export type MaterialsListData = {
  materials: MaterialItem[];
};

export type MaterialUploadItem = {
  file_name: string;
  status: "success" | "error";
  material_id: string | null;
  events_count: number;
  error_message: string | null;
};

export type MaterialUploadData = {
  items: MaterialUploadItem[];
  total_files: number;
  success_count: number;
};
