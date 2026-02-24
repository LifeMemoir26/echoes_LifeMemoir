"use client";

import { useQuery } from "@tanstack/react-query";
import { listEvents, listProfiles, listMaterials, getMaterialContent } from "@/lib/api/knowledge";
import type { EventItem, ProfileData, MaterialItem } from "@/lib/api/knowledge";
import { knowledgeQueryKeys } from "@/lib/query-keys";

export function useKnowledgeEvents() {
  return useQuery<{ events: EventItem[] }>({
    queryKey: knowledgeQueryKeys.events,
    queryFn: listEvents,
    staleTime: 600_000
  });
}

export function useKnowledgeProfiles() {
  return useQuery<ProfileData>({
    queryKey: knowledgeQueryKeys.profiles,
    queryFn: listProfiles,
    staleTime: 600_000
  });
}

export function useKnowledgeMaterials() {
  return useQuery<{ materials: MaterialItem[] }>({
    queryKey: knowledgeQueryKeys.materials,
    queryFn: listMaterials,
    staleTime: 600_000
  });
}

export function useKnowledgeMaterialContent(materialId: string | null) {
  return useQuery<{ content: string }>({
    queryKey: knowledgeQueryKeys.materialContent(materialId),
    queryFn: () => getMaterialContent(materialId!),
    enabled: !!materialId,
    staleTime: Infinity,
  });
}
