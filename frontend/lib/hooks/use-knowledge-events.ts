"use client";

import { useQuery } from "@tanstack/react-query";
import { listEvents, listProfiles, listMaterials, getMaterialContent } from "@/lib/api/knowledge-browser";
import type { EventItem, ProfileData, MaterialItem } from "@/lib/api/knowledge-browser";

export function useKnowledgeEvents() {
  return useQuery<{ events: EventItem[] }>({
    queryKey: ["knowledge", "events"],
    queryFn: listEvents,
    staleTime: 600_000
  });
}

export function useKnowledgeProfiles() {
  return useQuery<ProfileData>({
    queryKey: ["knowledge", "profiles"],
    queryFn: listProfiles,
    staleTime: 600_000
  });
}

export function useKnowledgeMaterials() {
  return useQuery<{ materials: MaterialItem[] }>({
    queryKey: ["materials"],
    queryFn: listMaterials,
    staleTime: 600_000
  });
}

export function useKnowledgeMaterialContent(materialId: string | null) {
  return useQuery<{ content: string }>({
    queryKey: ["material-content", materialId],
    queryFn: () => getMaterialContent(materialId!),
    enabled: !!materialId,
    staleTime: Infinity,
  });
}
