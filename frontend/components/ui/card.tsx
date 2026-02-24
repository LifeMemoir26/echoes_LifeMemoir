import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-black/[0.06] bg-white/80 p-6",
        "backdrop-blur-[15px] backdrop-saturate-[1.8]",
        "shadow-[var(--shadow-card)]",
        "transition-all duration-200",
        "hover:shadow-[var(--shadow-card-hover)] hover:-translate-y-px",
        className
      )}
      {...props}
    />
  );
}
