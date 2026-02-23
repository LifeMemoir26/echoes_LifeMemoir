"use client";

import type { EventSupplementItem } from "@/lib/api/types";

interface Props {
  supplements: EventSupplementItem[];
}

export function BackgroundSupplementPanel({ supplements }: Props) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <p className="mb-3 shrink-0 text-xs uppercase tracking-[0.16em] text-[#A2845E]">背景补充</p>
      {supplements.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted-fg)] text-center px-4">
          开始采访，发送几条消息后辅助内容将自动出现
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          {supplements.map((item, i) => (
            <div
              key={i}
              className="rounded-lg border border-[var(--border)] bg-white p-3 shadow-sm"
            >
              <p className="text-sm font-medium text-[var(--fg)] leading-snug">
                {item.event_summary}
              </p>
              <p className="text-xs text-[var(--muted-fg)] mt-1 leading-relaxed">
                {item.event_details}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
