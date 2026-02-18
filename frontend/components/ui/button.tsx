import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils/cn";
import type { ButtonHTMLAttributes } from "react";

const buttonVariants = cva(
  "focus-visible-ring inline-flex min-h-11 items-center justify-center rounded-[var(--radius)] px-6 text-xs font-medium uppercase tracking-[0.15em] transition duration-[var(--dur-base)] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--brass-gradient)] text-[var(--accent-fg)] [text-shadow:var(--engraved-text)] shadow-[inset_0_1px_0_rgba(255,255,255,0.2),inset_0_-1px_0_rgba(0,0,0,0.2),0_2px_8px_rgba(0,0,0,0.3)] hover:brightness-110",
        secondary:
          "border-2 border-[var(--accent)] bg-transparent text-[var(--accent)] hover:border-[var(--accent-2)] hover:bg-[var(--accent-2)] hover:text-[var(--fg)]",
        ghost:
          "bg-transparent text-[var(--accent)] underline-offset-4 hover:underline"
      },
      size: {
        sm: "h-10 px-5",
        md: "h-12 px-8",
        lg: "h-14 px-10"
      }
    },
    defaultVariants: {
      variant: "primary",
      size: "md"
    }
  }
);

type Props = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: Props) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
