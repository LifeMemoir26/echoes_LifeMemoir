export function formatEventYearLabel(year: string, timeDetail: string | null | undefined): string {
  if (year === "9999") {
    const detail = (timeDetail ?? "").trim();
    return detail || "时间待补充";
  }
  return year;
}
