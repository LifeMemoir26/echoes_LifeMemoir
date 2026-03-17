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
import { GeneratingHint, GeneratingLabel } from "@/components/ui/generation-indicator";
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

function splitMemoirBlocks(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
}

function MemoirBody({ text }: { text: string }) {
  return (
    <article className="memoir-prose text-slate-800">
      {splitMemoirBlocks(text).map((block, index) =>
        block === "✦" ? (
          <div key={`divider-${index}`} className="memoir-divider ornament-divider my-8">
            <span className="font-[var(--font-display)] text-base text-[#C4A882]">
              ✦
            </span>
          </div>
        ) : (
          <p key={`paragraph-${index}`}>{block}</p>
        )
      )}
    </article>
  );
}

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
    if (memoir.isLocked || inFlightRef.current) return;
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
      <main className="mx-auto max-w-3xl px-6 py-8">
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
                disabled={memoir.isLocked || !username}
                aria-label="生成回忆录"
              >
                <Sparkles className="mr-2 h-4 w-4" />
                {memoir.isPending ? <GeneratingLabel text="生成中" /> : "生成回忆录"}
              </Button>
            </div>
          </div>
        </form>

        {memoir.isPending && (
          <GeneratingHint text="正在生成回忆录，通常需要 30 到 90 秒" />
        )}

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
              <div className="relative overflow-hidden rounded-[30px] border border-[#E8DDD0] bg-[linear-gradient(180deg,rgba(255,255,255,0.97),rgba(247,242,235,0.94))] px-5 py-6 shadow-[0_28px_80px_rgba(120,90,60,0.14)] backdrop-blur-[10px] sm:px-8 sm:py-8">
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute -left-12 bottom-8 h-28 w-28 rounded-full bg-[#F6EBDD] blur-3xl"
                />
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute -right-10 top-6 h-32 w-32 rounded-full bg-[#F3E6D6] blur-3xl"
                />
                {/* Title ornament */}
                <div className="relative mb-8 text-center">
                  <p className="font-[var(--font-display)] text-2xl tracking-[0.18em] text-[#B79267] sm:text-3xl">
                    回忆录
                  </p>
                  <div className="ornament-divider mt-3">
                    <span className="font-[var(--font-display)] text-lg">✦</span>
                  </div>
                </div>

                <div className="relative mx-auto max-w-2xl rounded-[24px] border border-white/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.78),rgba(255,255,255,0.60))] px-6 py-8 shadow-[inset_0_1px_0_rgba(255,255,255,0.78)] sm:px-10 sm:py-10">
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-y-8 left-4 w-px bg-gradient-to-b from-transparent via-[#E6D9C7] to-transparent"
                  />
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-y-8 right-4 w-px bg-gradient-to-b from-transparent via-[#E6D9C7] to-transparent"
                  />
                  <MemoirBody text={memoir.data.memoir} />
                </div>

                <div className="mt-8 border-t border-black/[0.06] pt-5">
                  <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-slate-400">
                    <span>共 <span className="font-semibold text-[#A2845E]">{memoir.data.length}</span> 字</span>
                    {memoir.data.generated_at && (
                      <span>生成于 {memoir.data.generated_at.slice(0, 10)}</span>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          ) : !memoir.isLocked ? (
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
