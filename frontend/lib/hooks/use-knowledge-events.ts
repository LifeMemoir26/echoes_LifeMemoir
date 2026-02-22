"use client";

import { useQuery } from "@tanstack/react-query";
import { listEvents, listProfiles, listMaterials } from "@/lib/api/knowledge-browser";
import type { EventItem, ProfileData, MaterialItem } from "@/lib/api/knowledge-browser";

export function useKnowledgeEvents() {
  return useQuery<{ events: EventItem[] }>({
    queryKey: ["knowledge", "events"],
    queryFn: listEvents,
    staleTime: 60_000
  });
}

export function useKnowledgeProfiles() {
  return useQuery<ProfileData>({
    queryKey: ["knowledge", "profiles"],
    queryFn: listProfiles,
    staleTime: 60_000
  });
}

export function useKnowledgeMaterials() {
  return useQuery<{ materials: MaterialItem[] }>({
    queryKey: ["materials"],
    queryFn: listMaterials,
    staleTime: 30_000
  });
}
