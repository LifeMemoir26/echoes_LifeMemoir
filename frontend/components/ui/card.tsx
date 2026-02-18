import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-alt)] p-8 transition duration-[var(--dur-base)] hover:border-[color:color-mix(in_oklab,var(--accent)_50%,var(--border))] hover:shadow-[0_8px_24px_rgba(0,0,0,0.3)]",
        className
      )}
      {...props}
    />
  );
}
