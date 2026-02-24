export const knowledgeQueryKeys = {
  events: ["knowledge", "events"] as const,
  profiles: ["knowledge", "profiles"] as const,
  materials: ["knowledge", "materials"] as const,
  materialContent: (materialId: string | null) => ["knowledge", "material-content", materialId] as const,
};
