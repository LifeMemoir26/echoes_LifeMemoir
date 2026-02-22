import { apiGet, ApiRequestError, parseEnvelope, normalizeApiError, getAuthHeaders } from "@/lib/api/client";
import type { ApiError } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

export interface RecordItem {
  chunk_id: number;
  chunk_source: string | null;
  preview: string;
  total_chars: number;
  chunk_index: number;
  created_at: string;
  is_structured: boolean;
}

export interface RecordsListData {
  records: RecordItem[];
}

export interface EventItem {
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
}

export interface EventsListData {
  events: EventItem[];
}

export interface ProfileData {
  personality: string;
  worldview: string;
}

export interface MaterialItem {
  id: string;
  filename: string;
  material_type: string;
  material_context: string;
  file_path: string | null;
  file_size: number;
  status: "pending" | "processing" | "done" | "failed";
  events_count: number;
  chunks_count: number;
  uploaded_at: string;
  processed_at: string | null;
}

export interface MaterialsListData {
  materials: MaterialItem[];
}

export interface MaterialUploadItem {
  file_name: string;
  status: "success" | "error";
  material_id: string | null;
  events_count: number;
  error_message: string | null;
}

export interface MaterialUploadData {
  items: MaterialUploadItem[];
  total_files: number;
  success_count: number;
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

export function listRecords(): Promise<RecordsListData> {
  return apiGet<RecordsListData>("/knowledge/records");
}

export function listEvents(): Promise<EventsListData> {
  return apiGet<EventsListData>("/knowledge/events");
}

export function listProfiles(): Promise<ProfileData> {
  return apiGet<ProfileData>("/knowledge/profiles");
}

export function listMaterials(): Promise<MaterialsListData> {
  return apiGet<MaterialsListData>("/knowledge/materials");
}

export async function uploadMaterial(
  username: string,
  files: File[],
  materialContext: string = ""
): Promise<MaterialUploadData> {
  const formData = new FormData();
  formData.append("username", username);
  formData.append("material_context", materialContext);
  for (const file of files) {
    formData.append("files", file);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/knowledge/upload-material`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });
  } catch {
    throw new ApiRequestError({
      code: "NETWORK_ERROR",
      message: "无法连接后端服务，请检查后端是否已启动",
      retryable: true,
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
        retryable: false,
      });
    }
  }

  const envelope = parseEnvelope<MaterialUploadData>(json);
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
    retryable: false,
  });
}
