import { apiDelete, apiPost } from "@/lib/api/client";
import type {
  SessionActionData,
  SessionCloseData,
  SessionCreateData,
  SessionCreateRequest,
  SessionMessageRequest
} from "@/lib/api/types";

export async function createInterviewSession(payload: SessionCreateRequest): Promise<SessionCreateData> {
  return apiPost<SessionCreateData, SessionCreateRequest>("/session/create", payload);
}

export async function sendInterviewMessage(
  sessionId: string,
  payload: SessionMessageRequest
): Promise<SessionActionData> {
  return apiPost<SessionActionData, SessionMessageRequest>(`/session/${sessionId}/message`, payload);
}

export async function flushInterviewSession(sessionId: string): Promise<SessionActionData> {
  return apiPost<SessionActionData, Record<string, never>>(`/session/${sessionId}/flush`, {});
}

export async function closeInterviewSession(sessionId: string): Promise<SessionCloseData> {
  return apiDelete<SessionCloseData>(`/session/${sessionId}`);
}
