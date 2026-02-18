"use client";

import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { BookText, Feather, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { useGenerateMemoir } from "@/lib/hooks/use-generate-memoir";

const formSchema = z.object({
  username: z.string().min(1, "请输入用户名"),
  target_length: z.coerce.number().min(200, "最少 200 字").max(100000, "最多 100000 字"),
  user_preferences: z.string().optional()
});

type FormValues = z.infer<typeof formSchema>;

export function MemoirReaderPage() {
  const { register, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      username: "",
      target_length: 2000,
      user_preferences: "温暖、克制、重视家庭细节"
    }
  });

  const { mutateAsync, data, normalizedError, isPending, canRetry } = useGenerateMemoir();

  const statusLabel = useMemo(() => {
    if (isPending) return { status: "loading" as const, text: "生成中" };
    if (data) return { status: "success" as const, text: "生成完成" };
    if (normalizedError) return { status: "error" as const, text: "生成失败" };
    return { status: "idle" as const, text: "待开始" };
  }, [data, isPending, normalizedError]);

  const onSubmit = handleSubmit(async (values) => {
    if (isPending) return;
    await mutateAsync({
      username: values.username,
      target_length: values.target_length,
      user_preferences: values.user_preferences,
      auto_save: true
    });
  });

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-4 py-10 md:px-8 md:py-16">
      <section className="mb-8 rounded-[var(--radius)] border border-[var(--border)] bg-[color:color-mix(in_oklab,var(--bg-alt)_80%,transparent)] p-6 md:p-10">
        <p className="mb-4 font-[var(--font-display)] text-xs uppercase tracking-[0.26em] text-[var(--accent)]">Volume I</p>
        <h1 className="mb-3 font-[var(--font-heading)] text-4xl leading-[1.1] md:text-6xl">回忆录阅读</h1>
        <p className="max-w-3xl text-base text-[var(--muted-fg)] md:text-lg">
          在沉静而温暖的阅读空间中，生成并细读你的生命叙事。页面采用中度装饰的学院风格，保证情感表达同时维持高可读性。
        </p>
      </section>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: "easeOut" }}>
          <Card className="mb-6">
            <form className="grid gap-4 md:grid-cols-2" onSubmit={onSubmit}>
              <label className="md:col-span-1">
                <span className="mb-2 block font-[var(--font-display)] text-xs uppercase tracking-[0.2em] text-[var(--muted-fg)]">用户名</span>
                <Input aria-label="用户名" {...register("username")} />
              </label>

              <label className="md:col-span-1">
                <span className="mb-2 block font-[var(--font-display)] text-xs uppercase tracking-[0.2em] text-[var(--muted-fg)]">目标字数</span>
                <Input aria-label="目标字数" type="number" {...register("target_length")} />
              </label>

              <label className="md:col-span-2">
                <span className="mb-2 block font-[var(--font-display)] text-xs uppercase tracking-[0.2em] text-[var(--muted-fg)]">叙事偏好</span>
                <Input aria-label="叙事偏好" {...register("user_preferences")} />
              </label>

              {formState.errors.username ? <p className="text-sm text-[var(--accent-2)]">{formState.errors.username.message}</p> : null}

              <div className="md:col-span-2 flex flex-wrap items-center gap-3">
                <Button type="submit" disabled={isPending} aria-label="生成回忆录">
                  <Sparkles className="mr-2 h-4 w-4" />
                  {isPending ? "生成中" : "生成回忆录"}
                </Button>
              </div>
            </form>
          </Card>

          <Card>
            <div className="mb-4 flex items-center gap-3">
              <BookText className="h-5 w-5 text-[var(--accent)]" />
              <h2 className="font-[var(--font-heading)] text-2xl">正文</h2>
            </div>
            <div className="ornate-divider mb-6" aria-hidden="true" />

            {normalizedError ? (
              <ErrorBanner
                code={normalizedError.code}
                message={normalizedError.message}
                retryable={normalizedError.retryable}
                traceId={normalizedError.traceId}
                retrying={isPending}
                onRetry={
                  canRetry
                    ? () => {
                        void onSubmit();
                      }
                    : undefined
                }
              />
            ) : null}

            {data ? (
              <article className="space-y-5 text-lg leading-relaxed text-[var(--fg)]">
                <p className="drop-cap">{data.memoir}</p>
              </article>
            ) : (
              <p className="text-base text-[var(--muted-fg)]">尚未生成内容。填写信息后点击“生成回忆录”。</p>
            )}
          </Card>
        </motion.section>

        <aside className="space-y-4">
          <Card>
            <p className="mb-3 font-[var(--font-display)] text-xs uppercase tracking-[0.25em] text-[var(--accent)]">Volume II</p>
            <h3 className="mb-4 font-[var(--font-heading)] text-2xl">状态与元信息</h3>
            <StatusBadge status={statusLabel.status} label={statusLabel.text} />
            <div className="mt-4 space-y-2 text-sm text-[var(--muted-fg)]" aria-live="polite">
              <p className="flex items-center gap-2">
                <Feather className="h-4 w-4 text-[var(--accent)]" />
                长度: {data?.length ?? "-"}
              </p>
              <p>生成时间: {data?.generated_at ?? "-"}</p>
              <p>Trace ID: {data?.trace_id ?? normalizedError?.traceId ?? "-"}</p>
            </div>
          </Card>
        </aside>
      </div>
    </main>
  );
}
