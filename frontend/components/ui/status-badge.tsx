import { CheckCircle2, AlertTriangle, Clock3 } from "lucide-react";
import { cn } from "@/lib/utils/cn";

type Props = {
  status: "idle" | "loading" | "success" | "error";
  label: string;
};

export function StatusBadge({ status, label }: Props) {
  const iconClass = "h-4 w-4";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.08em]",
        status === "success" && "border-emerald-200 bg-emerald-50 text-emerald-700",
        status === "error" && "border-rose-200 bg-rose-50 text-rose-700",
        status === "loading" && "border-[#C4A882] bg-[#F5EDE4] text-[#7A6242]",
        status === "idle" && "border-slate-200 bg-slate-50 text-slate-500"
      )}
    >
      {(status === "success" && <CheckCircle2 className={iconClass} />) ||
        (status === "error" && <AlertTriangle className={iconClass} />) ||
        <Clock3 className={iconClass} />}
      <span>{label}</span>
    </div>
  );
}
