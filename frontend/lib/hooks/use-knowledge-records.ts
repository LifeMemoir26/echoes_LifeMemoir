"use client";

import { useQuery } from "@tanstack/react-query";
import { listRecords } from "@/lib/api/knowledge-browser";
import type { RecordItem } from "@/lib/api/knowledge-browser";

export function useKnowledgeRecords() {
  return useQuery<{ records: RecordItem[] }>({
    queryKey: ["knowledge", "records"],
    queryFn: listRecords,
    staleTime: 60_000
  });
}
