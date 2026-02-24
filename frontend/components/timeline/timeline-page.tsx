"use client";

import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarDays, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { useGenerateTimeline } from "@/lib/hooks/use-generate-timeline";
import { useWorkspaceContext } from "@/lib/workspace/context";

const formSchema = z.object({
  timeline_ratio: z.coerce.number().min(0, "最小 0").max(1, "最大 1"),
  user_preferences: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

export function TimelinePage() {
  const { username } = useWorkspaceContext();
  const timeline = useGenerateTimeline();

  const { register, getValues } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      timeline_ratio: 0.3,
    },
  });

  const handleGenerate = async () => {
    const values = getValues();
    await timeline.submit({
      username: username ?? "",
      ratio: values.timeline_ratio,
      user_preferences: values.user_preferences,
      auto_save: true,
    });
  };

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
        <div className="flex flex-wrap items-end gap-4 pb-5 border-b border-black/[0.08]">
          <label className="flex flex-col gap-1 min-w-[100px]">
            <span className="text-xs uppercase tracking-[0.16em] text-slate-400">
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
            <span className="text-xs uppercase tracking-[0.16em] text-slate-400">
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
              type="button"
              onClick={() => void handleGenerate()}
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
        </div>

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
          {timeline.data?.timeline?.length ? (
            <div className="border-l-2 border-[#C4A882] pl-4 space-y-6">
              {timeline.data.timeline.map((event, idx) => (
                <div key={idx}>
                  <p className="font-[var(--font-heading)] text-lg text-[#A2845E]">
                    {event.time}
                  </p>
                  <p className="mt-1 text-slate-700">
                    {event.objective_summary}
                  </p>
                  <p className="mt-1.5 text-sm text-slate-500 leading-relaxed italic">
                    {event.detailed_narrative}
                  </p>
                </div>
              ))}
            </div>
          ) : !timeline.isPending ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-4">
                <CalendarDays className="h-8 w-8 text-[#A2845E]" />
              </div>
              <p className="text-sm text-slate-500">尚未生成时间线</p>
              <p className="mt-1 text-xs text-slate-400">
                点击上方「生成时间线」开始梳理你的人生轨迹
              </p>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
