"use client";

import { useRef } from "react";
import type { FormEvent } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { BookOpen, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { useGenerateMemoir } from "@/lib/hooks/use-generate-memoir";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { smooth, softSpring } from "@/lib/motion/spring";

const formSchema = z.object({
  target_length: z.coerce
    .number()
    .min(200, "最少 200 字")
    .max(100000, "最多 100000 字"),
  user_preferences: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

export function MemoirPage() {
  const { username } = useWorkspaceContext();
  const memoir = useGenerateMemoir();
  const inFlightRef = useRef(false);

  const { register, handleSubmit } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      target_length: 2000,
    },
  });

  const onMemoirSubmit = handleSubmit(async (values) => {
    await memoir.mutateAsync({
      username: username ?? "",
      target_length: values.target_length,
      user_preferences: values.user_preferences,
      auto_save: true,
    });
  });

  const onFormSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (memoir.isPending || inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      await onMemoirSubmit(event);
    } catch {
      // normalized in hook
    } finally {
      inFlightRef.current = false;
    }
  };

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-2xl px-6 py-8">
        {/* Page heading */}
        <div className="mb-6">
          <h1 className="font-[var(--font-heading)] text-3xl text-slate-900">
            回忆录
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            将你的故事编织成完整的叙事
          </p>
        </div>
        {/* Inline parameter bar */}
        <form onSubmit={onFormSubmit}>
          <div className="flex flex-wrap items-end gap-4 pb-5 border-b border-black/[0.08]">
            <label className="flex flex-col gap-1 min-w-[120px]">
              <span className="panel-label text-slate-400">
                目标字数
              </span>
              <Input
                aria-label="目标字数"
                type="number"
                {...register("target_length")}
                className="w-28"
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
                disabled={memoir.isPending || !username}
                aria-label="生成回忆录"
              >
                <Sparkles className="mr-2 h-4 w-4" />
                {memoir.isPending ? "生成中" : "生成回忆录"}
              </Button>
            </div>
          </div>
        </form>

        {/* Error banner */}
        {memoir.normalizedError && (
          <div className="mt-5">
            <ErrorBanner
              code={memoir.normalizedError.code}
              message={memoir.normalizedError.message}
              retryable={memoir.normalizedError.retryable}
              traceId={memoir.normalizedError.traceId}
              retrying={memoir.isPending}
              onRetry={
                memoir.canRetry ? () => void onMemoirSubmit() : undefined
              }
            />
          </div>
        )}

        {/* Memoir body */}
        <div className="mt-8">
          {memoir.data ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={smooth}
            >
              {/* Paper container */}
              <div className="rounded-2xl border border-black/[0.06] bg-white/90 px-8 py-10 shadow-[var(--shadow-perfect)] backdrop-blur-[10px] sm:px-12 sm:py-14">
                {/* Title ornament */}
                <div className="mb-8 text-center">
                  <p className="font-[var(--font-display)] text-xs uppercase tracking-[0.3em] text-[#C4A882]">
                    回忆录
                  </p>
                  <div className="ornament-divider mt-3">
                    <span className="font-[var(--font-display)] text-lg">✦</span>
                  </div>
                </div>

                {/* Prose body — split paragraphs on double-newline */}
                <article className="memoir-prose text-slate-800">
                  {memoir.data.memoir.split(/\n{2,}/).map((para, i) => (
                    <p key={i}>{para}</p>
                  ))}
                </article>

                {/* Bottom ornament */}
                <div className="ornament-divider mt-10">
                  <span className="font-[var(--font-display)] text-lg">✦</span>
                </div>
              </div>

              {/* Metadata footer */}
              <div className="mt-6 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-slate-400">
                <span>共 <span className="font-semibold text-[#A2845E]">{memoir.data.length}</span> 字</span>
                {memoir.data.generated_at && (
                  <span>生成于 {memoir.data.generated_at.slice(0, 10)}</span>
                )}
                {memoir.data.trace_id && (
                  <span className="font-mono text-[10px] text-slate-300">
                    Trace: {memoir.data.trace_id}
                  </span>
                )}
              </div>
            </motion.div>
          ) : !memoir.isPending ? (
            <motion.div
              className="flex flex-col items-center justify-center py-16 text-center"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={softSpring}
            >
              <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-4">
                <BookOpen className="h-8 w-8 text-[#C4A882] opacity-60" />
              </div>
              <p className="text-sm italic text-slate-500">尚未生成内容</p>
              <p className="mt-1 text-xs text-slate-400">
                点击上方「生成回忆录」将你的故事编织成完整叙事
              </p>
            </motion.div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
