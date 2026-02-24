import { apiGet, apiPost, apiDelete, apiPostFormData } from "@/lib/api/client";
import type {
  EventItem,
  EventsListData,
  ProfileData,
  MaterialItem,
  MaterialsListData,
  MaterialUploadItem,
  MaterialUploadData,
} from "@/lib/api/types";

// Re-export types for backward compat with existing consumers
export type { EventItem, EventsListData, ProfileData, MaterialItem, MaterialsListData, MaterialUploadItem, MaterialUploadData };

export function listEvents(): Promise<EventsListData> {
  return apiGet<EventsListData>("/knowledge/events");
}

export function listProfiles(): Promise<ProfileData> {
  return apiGet<ProfileData>("/knowledge/profiles");
}

export function listMaterials(): Promise<MaterialsListData> {
  return apiGet<MaterialsListData>("/knowledge/materials");
}

export function getMaterialContent(materialId: string): Promise<{ content: string }> {
  return apiGet<{ content: string }>(`/knowledge/materials/${materialId}/content`);
}

export function triggerReprocess(materialId: string): Promise<{ material_id: string; trace_id: string }> {
  return apiPost<{ material_id: string; trace_id: string }, Record<string, never>>(
    `/knowledge/materials/${materialId}/reprocess`,
    {}
  );
}

export async function uploadMaterial(
  username: string,
  files: File[],
  materialContext: string = "",
  displayName: string = "",
  skipProcessing: boolean = false,
  materialType: "interview" | "document" = "document"
): Promise<MaterialUploadData> {
  const formData = new FormData();
  formData.append("username", username);
  formData.append("material_context", materialContext);
  formData.append("display_name", displayName);
  formData.append("material_type", materialType);
  if (skipProcessing) {
    formData.append("skip_processing", "true");
  }
  for (const file of files) {
    formData.append("files", file);
  }

  return apiPostFormData<MaterialUploadData>("/knowledge/upload-material", formData);
}

export function deleteMaterial(materialId: string): Promise<{ material_id: string }> {
  return apiDelete<{ material_id: string }>(`/knowledge/materials/${materialId}`);
}

export function cancelStructuring(materialId: string): Promise<{ material_id: string; was_active: boolean }> {
  return apiPost<{ material_id: string; was_active: boolean }, Record<string, never>>(
    `/knowledge/materials/${materialId}/cancel`,
    {}
  );
}
