import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils/cn";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "focus-visible-ring h-12 w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-alt)] px-4 py-2 text-[var(--fg)] placeholder:italic placeholder:text-[var(--muted-fg)]",
        className
      )}
      {...props}
    />
  );
}
