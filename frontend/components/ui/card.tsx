import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-6 transition duration-[var(--dur-base)]",
        className
      )}
      {...props}
    />
  );
}
