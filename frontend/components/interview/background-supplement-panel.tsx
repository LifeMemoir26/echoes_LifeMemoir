"use client";

import type { EventSupplementItem } from "@/lib/api/types";

interface Props {
  supplements: EventSupplementItem[];
}

export function BackgroundSupplementPanel({ supplements }: Props) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <p className="mb-3 shrink-0 panel-label">背景补充</p>
      {supplements.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-sm italic text-slate-400 text-center px-4">
          开始采访，发送几条消息后辅助内容将自动出现
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto mask-fade-b space-y-3 pr-1 pt-1 pb-6">
          {supplements.map((item, i) => (
            <div
              key={i}
              className="rounded-xl border border-black/[0.06] bg-white/80 p-3.5 shadow-[var(--shadow-card)] backdrop-blur-sm transition-shadow duration-200 hover:shadow-[var(--shadow-card-hover)]"
            >
              <p className="text-sm font-medium text-slate-800 leading-snug">
                {item.event_summary}
              </p>
              <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                {item.event_details}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
