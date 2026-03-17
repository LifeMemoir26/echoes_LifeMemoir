"use client";

import { motion } from "framer-motion";

export function GeneratingLabel({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span>{text}</span>
      <span className="inline-flex items-end gap-1" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <motion.span
            key={index}
            className="h-1.5 w-1.5 rounded-full bg-current/70"
            animate={{ y: [0, -2, 0], opacity: [0.45, 1, 0.45] }}
            transition={{
              duration: 0.9,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
              delay: index * 0.12,
            }}
          />
        ))}
      </span>
    </span>
  );
}

export function GeneratingHint({ text }: { text: string }) {
  return (
    <p
      className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#F5EDE4]/80 px-3 py-1.5 text-sm text-[#8C6F49] shadow-[0_10px_30px_rgba(162,132,94,0.08)]"
    >
      <span className="h-2 w-2 rounded-full bg-[#C4A882]" />
      <span>{text}</span>
    </p>
  );
}
