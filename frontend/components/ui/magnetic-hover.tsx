"use client";

import { useCallback, useRef, type ReactNode, type ElementType, type ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils/cn";

type MagneticHoverProps<T extends ElementType = "div"> = {
  as?: T;
  children: ReactNode;
  /** Attraction strength — fraction of cursor-to-center distance (default 0.05 = 5%) */
  strength?: number;
} & Omit<ComponentPropsWithoutRef<T>, "as" | "children">;

/**
 * Wraps children in a container that subtly follows the cursor on hover,
 * creating a magnetic "pull" effect. Inspired by Shiro's MagneticHoverEffect.
 */
export function MagneticHover<T extends ElementType = "div">({
  as,
  children,
  strength = 0.05,
  className,
  ...rest
}: MagneticHoverProps<T>) {
  const Component = as || "div";
  const ref = useRef<HTMLElement>(null);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLElement>) => {
      if (!ref.current) return;
      const rect = ref.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const dx = (e.clientX - centerX) * strength;
      const dy = (e.clientY - centerY) * strength;
      ref.current.style.transform = `translate(${dx}px, ${dy}px)`;
    },
    [strength],
  );

  const handleMouseLeave = useCallback(() => {
    if (!ref.current) return;
    ref.current.style.transform = "translate(0px, 0px)";
  }, []);

  return (
    <Component
      ref={ref as never}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={cn(
        "transition-transform duration-200 ease-[cubic-bezier(0.33,1,0.68,1)] will-change-transform",
        className,
      )}
      {...rest}
    >
      {children}
    </Component>
  );
}
