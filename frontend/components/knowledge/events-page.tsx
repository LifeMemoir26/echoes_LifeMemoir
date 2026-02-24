"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CalendarDays, ChevronDown, ChevronUp } from "lucide-react";
import { useKnowledgeEvents } from "@/lib/hooks/use-knowledge-events";
import type { EventItem } from "@/lib/api/knowledge-browser";
import { softSpring } from "@/lib/motion/spring";

function EventCard({ item, index }: { item: EventItem; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...softSpring, delay: index * 0.04 }}
      className="rounded-xl border border-black/[0.06] bg-white/80 p-5 shadow-[var(--shadow-card)] backdrop-blur-sm transition-shadow duration-200 hover:shadow-[var(--shadow-card-hover)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Year + badges */}
          <div className="mb-1.5 flex items-center gap-2 flex-wrap">
            <span className="font-[var(--font-heading)] text-sm font-semibold text-[#A2845E]">
              {item.year}
            </span>
          </div>
          {/* Summary */}
          <p className="text-sm leading-relaxed text-slate-700">{item.event_summary}</p>
          {/* Category tags */}
          {item.event_category.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {item.event_category.map((cat) => (
                <span
                  key={cat}
                  className="rounded-full border border-black/[0.06] bg-white px-2.5 py-0.5 text-xs text-slate-500"
                >
                  {cat}
                </span>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex-shrink-0 cursor-pointer rounded-lg p-1.5 text-[#C4A882] transition-colors duration-150 hover:text-[#A2845E] hover:bg-[#F5EDE4]/50"
          aria-label={expanded ? "折叠" : "展开"}
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            key="expanded-event"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-4 max-h-64 space-y-2 overflow-y-auto border-t border-black/[0.06] pt-4">
              {item.time_detail && (
                <p className="text-xs text-slate-400">
                  <span className="font-medium text-slate-500">时间细节：</span>
                  {item.time_detail}
                </p>
              )}
              {item.event_details && (
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                  {item.event_details}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function EventsPage() {
  const eventsQuery = useKnowledgeEvents();

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-3xl px-6 py-8">
        {/* Page heading */}
        <div className="mb-6">
          <h1 className="font-[var(--font-heading)] text-3xl text-slate-900">
            人生事件
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            从采访与资料中提取的人生经历
          </p>
        </div>

        {/* Event list */}
        <div className="space-y-4">
          {eventsQuery.isLoading && (
            <p className="py-8 text-center text-sm text-slate-400">加载中…</p>
          )}
          {eventsQuery.isError && (
            <p className="py-8 text-center text-sm text-rose-500">加载失败，请刷新重试</p>
          )}
          {eventsQuery.data?.events.length === 0 && (
            <motion.div
              className="flex flex-col items-center justify-center py-16 text-center"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={softSpring}
            >
              <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-4">
                <CalendarDays className="h-8 w-8 text-[#C4A882] opacity-60" />
              </div>
              <p className="text-sm italic text-slate-500">暂无人生事件</p>
              <p className="mt-1 text-xs text-slate-400">
                通过采访或上传资料后进行结构化，人生事件将出现在此
              </p>
            </motion.div>
          )}
          {eventsQuery.data?.events.map((item, index) => (
            <EventCard key={item.id} item={item} index={index} />
          ))}
        </div>
      </main>
    </div>
  );
}
