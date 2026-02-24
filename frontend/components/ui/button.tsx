import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils/cn";
import type { ButtonHTMLAttributes } from "react";

const buttonVariants = cva(
  "focus-visible-ring inline-flex min-h-11 cursor-pointer items-center justify-center rounded-lg px-5 text-sm font-semibold transition-all duration-200 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-[#A2845E] text-white shadow-[var(--shadow-card)] hover:bg-[#8E7250] hover:shadow-[var(--shadow-card-hover)] hover:-translate-y-px active:translate-y-0",
        secondary: "border border-slate-300 bg-white text-slate-700 hover:border-[#C4A882] hover:text-[#A2845E] hover:shadow-[var(--shadow-card)]",
        ghost: "bg-transparent text-[#A2845E] hover:bg-[#A2845E]/[0.06]"
      },
      size: {
        sm: "h-10 px-4",
        md: "h-11 px-5",
        lg: "h-12 px-6"
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
