"use client";

import { motion } from "framer-motion";
import { usePathname } from "next/navigation";
import { smooth } from "@/lib/motion/spring";
import type { ReactNode } from "react";

export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <motion.div
      key={pathname}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={smooth}
      className="flex-1 overflow-auto"
    >
      {children}
    </motion.div>
  );
}
