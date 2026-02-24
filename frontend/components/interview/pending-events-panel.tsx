"use client";

import { useMemo } from "react";
import type { PendingEventDetail } from "@/lib/api/types";

interface Props {
  events: PendingEventDetail[];
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  onTogglePriority?: (id: string) => void;
}

/** Sort: priority first, then by explored_length ascending (less explored = higher). */
function sortedEvents(events: PendingEventDetail[]): PendingEventDetail[] {
  return [...events].sort((a, b) => {
    if (a.is_priority !== b.is_priority) return a.is_priority ? -1 : 1;
    return a.explored_length - b.explored_length;
  });
}

export function PendingEventsPanel({
  events,
  expandedIds,
  onToggle,
  onTogglePriority,
}: Props) {
  const sorted = useMemo(() => sortedEvents(events), [events]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="mb-3 shrink-0 flex items-baseline justify-between">
        <p className="panel-label">建议深挖事件</p>
        {sorted.length > 0 && (
          <span className="text-[10px] text-slate-400">
            点击 ▼ 展开 · 点击圆点设为优先
          </span>
        )}
      </div>
      {sorted.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-sm italic text-slate-400 text-center px-4">
          开始采访，发送几条消息后辅助内容将自动出现
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto mask-fade-b space-y-2 pr-1 pb-6">
          {sorted.map((event) => {
            const isOpen = expandedIds.has(event.id);
            return (
              <div
                key={event.id}
                className="rounded-xl border border-black/[0.06] bg-white/80 overflow-hidden shadow-[var(--shadow-card)] backdrop-blur-sm transition-shadow duration-200 hover:shadow-[var(--shadow-card-hover)]"
              >
                <div className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left">
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      onTogglePriority?.(event.id);
                    }}
                    className={`shrink-0 w-2.5 h-2.5 rounded-full cursor-pointer transition-all duration-100 hover:scale-[1.3] active:scale-150 ${
                      event.is_priority
                        ? "bg-[#A2845E] shadow-[0_0_0_2px_#F5EDE4]"
                        : "bg-slate-300/60 hover:bg-slate-400/60"
                    }`}
                    title={
                      event.is_priority
                        ? "取消优先"
                        : "设为优先"
                    }
                  />
                  <span className="flex-1 text-sm text-slate-800 leading-snug">
                    {event.summary}
                  </span>
                  <button
                    onClick={() => onToggle(event.id)}
                    className="shrink-0 p-1 -mr-1 rounded-md text-[#C4A882] text-xs transition-all duration-200 cursor-pointer hover:bg-[#F5EDE4]/50"
                    style={{ transform: isOpen ? "rotate(180deg)" : undefined }}
                    aria-label={isOpen ? "收起详情" : "展开详情"}
                  >
                    ▼
                  </button>
                </div>
                {isOpen && (
                  <div className="px-3.5 pb-3 pt-1.5 border-t border-black/[0.06]">
                    {event.explored_content ? (
                      <p className="text-xs text-slate-500 leading-relaxed whitespace-pre-wrap">
                        {event.explored_content}
                        {event.explored_length > 500 && (
                          <span className="italic text-slate-400">
                            {" "}
                            … (共 {event.explored_length} 字)
                          </span>
                        )}
                      </p>
                    ) : (
                      <p className="text-xs italic text-slate-400">尚未探索</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
