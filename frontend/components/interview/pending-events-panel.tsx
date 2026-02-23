"use client";

import type { PendingEventDetail } from "@/lib/api/types";

interface Props {
  events: PendingEventDetail[];
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}

export function PendingEventsPanel({ events, expandedIds, onToggle }: Props) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <p className="mb-3 shrink-0 text-xs uppercase tracking-[0.16em] text-[#A2845E]">建议深挖事件</p>
      {events.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted-fg)] text-center px-4">
          开始采访，发送几条消息后辅助内容将自动出现
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {events.map((event) => {
            const isOpen = expandedIds.has(event.id);
            return (
              <div key={event.id} className="rounded-lg border border-[var(--border)] bg-white overflow-hidden">
                <button
                  onClick={() => onToggle(event.id)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-50 transition-colors duration-150"
                >
                  {event.is_priority && (
                    <span className="shrink-0 w-2 h-2 rounded-full bg-[var(--accent-2)]" title="高优先级" />
                  )}
                  <span className="flex-1 text-sm text-[var(--fg)] leading-snug">{event.summary}</span>
                  <span className="shrink-0 text-[var(--muted-fg)] text-xs">{isOpen ? "▲" : "▼"}</span>
                </button>
                {isOpen && (
                  <div className="px-3 pb-3 pt-1 border-t border-[var(--border)]">
                    {event.explored_content ? (
                      <p className="text-xs text-[var(--muted-fg)] leading-relaxed whitespace-pre-wrap">
                        {event.explored_content}
                        {event.explored_length > 500 && (
                          <span className="italic">… (共 {event.explored_length} 字)</span>
                        )}
                      </p>
                    ) : (
                      <p className="text-xs text-[var(--muted-fg)] italic">尚未探索</p>
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
