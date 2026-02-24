"use client";

import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarDays, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { useGenerateTimeline } from "@/lib/hooks/use-generate-timeline";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { softSpring } from "@/lib/motion/spring";

const formSchema = z.object({
  timeline_ratio: z.coerce.number().min(0, "最小 0").max(1, "最大 1"),
  user_preferences: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

export function TimelinePage() {
  const { username } = useWorkspaceContext();
  const timeline = useGenerateTimeline();

  const { register, handleSubmit } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      timeline_ratio: 0.3,
    },
  });

  const onGenerate = handleSubmit(async (values) => {
    await timeline.submit({
      username: username ?? "",
      ratio: values.timeline_ratio,
      user_preferences: values.user_preferences,
      auto_save: true,
    });
  });

  const events = timeline.data?.timeline;

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-2xl px-6 py-8">
        {/* Page heading */}
        <div className="mb-6">
          <h1 className="font-[var(--font-heading)] text-3xl text-slate-900">
            时间轴
          </h1>
          <p className="mt-1 text-sm text-slate-500">按时间顺序梳理人生事件</p>
        </div>
        {/* Inline parameter bar */}
        <form onSubmit={onGenerate} className="flex flex-wrap items-end gap-4 pb-5 border-b border-black/[0.08]">
          <label className="flex flex-col gap-1 min-w-[100px]">
            <span className="panel-label text-slate-400">
              时间线比例
            </span>
            <Input
              aria-label="时间线比例"
              type="number"
              step="0.1"
              {...register("timeline_ratio")}
              className="w-24"
            />
          </label>
          <label className="flex flex-col gap-1 flex-1 min-w-[200px]">
            <span className="panel-label text-slate-400">
              叙事偏好
            </span>
            <Input
              aria-label="叙事偏好"
              placeholder="温暖、平静、有希望"
              {...register("user_preferences")}
            />
          </label>
          <div className="flex items-center gap-2 pb-0.5">
            <Button
              type="submit"
              disabled={timeline.isPending || !username}
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {timeline.isPending ? "生成中" : "生成时间线"}
            </Button>
            {timeline.canRetry && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => void timeline.retry()}
                disabled={timeline.isPending}
              >
                重试
              </Button>
            )}
          </div>
        </form>

        {/* Error banner */}
        {timeline.error && (
          <div className="mt-5">
            <ErrorBanner
              code={timeline.error.code}
              message={timeline.error.message}
              retryable={timeline.error.retryable}
              traceId={timeline.error.traceId}
            />
          </div>
        )}

        {/* Timeline event list */}
        <div className="mt-8">
          {events?.length ? (
            <>
              {/* Dot-node timeline */}
              <div className="timeline-track space-y-8">
                {events.map((event, idx) => (
                  <motion.div
                    key={idx}
                    className="timeline-node"
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ ...softSpring, delay: idx * 0.06 }}
                  >
                    {/* Time badge */}
                    <span className="inline-block rounded-full bg-[#F5EDE4] px-3 py-0.5 font-[var(--font-heading)] text-sm text-[#A2845E]">
                      {event.time}
                    </span>

                    {/* Event card */}
                    <div className="mt-2 rounded-xl border border-black/[0.06] bg-white/80 px-5 py-4 shadow-[var(--shadow-card)] backdrop-blur-[10px]">
                      <h3 className="font-[var(--font-heading)] text-lg leading-snug text-slate-800">
                        {event.objective_summary}
                      </h3>
                      <p className="mt-2 text-sm leading-relaxed text-slate-500 italic">
                        {event.detailed_narrative}
                      </p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </>
          ) : !timeline.isPending ? (
            <motion.div
              className="flex flex-col items-center justify-center py-16 text-center"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={softSpring}
            >
              <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-4">
                <CalendarDays className="h-8 w-8 text-[#C4A882] opacity-60" />
              </div>
              <p className="text-sm italic text-slate-500">尚未生成时间线</p>
              <p className="mt-1 text-xs text-slate-400">
                点击上方「生成时间线」开始梳理你的人生轨迹
              </p>
            </motion.div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
