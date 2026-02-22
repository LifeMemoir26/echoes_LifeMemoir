import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils/cn";
import type { ButtonHTMLAttributes } from "react";

const buttonVariants = cva(
  "focus-visible-ring inline-flex min-h-11 items-center justify-center rounded-lg px-5 text-sm font-semibold transition duration-[var(--dur-base)] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-[#A2845E] text-white hover:bg-[#8E7250] shadow-sm",
        secondary: "border border-slate-300 bg-white text-slate-700 hover:border-[#C4A882] hover:text-[#A2845E]",
        ghost: "bg-transparent text-[#A2845E] hover:bg-[#F5EDE4]"
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
