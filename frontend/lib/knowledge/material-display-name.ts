import type { MaterialItem } from "@/lib/api/types";

export function resolveMaterialDisplayName(item: Pick<MaterialItem, "material_type" | "display_name" | "filename">): string {
  if (item.material_type === "interview") {
    return "采访记录";
  }
  return item.display_name || item.filename;
}

function parseUploadedAtAsUtc(uploadedAt: string): Date | null {
  const raw = uploadedAt.trim();
  if (!raw) return null;

  // If timezone info exists, trust native parser.
  if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(raw)) {
    const withZone = new Date(raw);
    return Number.isNaN(withZone.getTime()) ? null : withZone;
  }

  // Backend DB commonly returns "YYYY-MM-DD HH:mm:ss" (UTC, without timezone).
  const match = raw.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2})(?::(\d{2})(?::(\d{2}))?)?)?$/,
  );
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const hour = Number(match[4] ?? "0");
    const minute = Number(match[5] ?? "0");
    const second = Number(match[6] ?? "0");
    return new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  }

  const fallback = new Date(raw);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

export function formatArchiveAtHour(uploadedAt: string): string {
  const d = parseUploadedAtAsUtc(uploadedAt);
  if (!d) return uploadedAt;

  // Always render archive time in UTC+8.
  const utc8 = new Date(d.getTime() + 8 * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${utc8.getUTCFullYear()}-${pad(utc8.getUTCMonth() + 1)}-${pad(utc8.getUTCDate())} ${pad(utc8.getUTCHours())}:00`;
}
