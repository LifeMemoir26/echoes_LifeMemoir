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
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs uppercase tracking-[0.12em]",
        status === "success" && "border-[var(--accent)] text-[var(--accent)]",
        status === "error" && "border-[var(--accent-2)] text-[var(--accent-2)]",
        status === "loading" && "border-[var(--muted-fg)] text-[var(--muted-fg)]",
        status === "idle" && "border-[var(--border)] text-[var(--muted-fg)]"
      )}
    >
      {status === "success" && <CheckCircle2 className={iconClass} />}
      {status === "error" && <AlertTriangle className={iconClass} />}
      {status === "loading" && <Clock3 className={iconClass} />}
      {status === "idle" && <Clock3 className={iconClass} />}
      <span>{label}</span>
    </div>
  );
}
