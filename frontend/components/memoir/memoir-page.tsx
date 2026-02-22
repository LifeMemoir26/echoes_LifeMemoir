"use client";

import { useRef } from "react";
import type { FormEvent } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { normalizeUnknownError } from "@/lib/api/client";
import { processKnowledgeFile } from "@/lib/api/knowledge";
import { useGenerateMemoir } from "@/lib/hooks/use-generate-memoir";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { useState } from "react";
import type { NormalizedApiError } from "@/lib/api/types";

const formSchema = z.object({
  target_length: z.coerce.number().min(200, "最少 200 字").max(100000, "最多 100000 字"),
  user_preferences: z.string().optional()
});

type FormValues = z.infer<typeof formSchema>;

export function MemoirPage() {
  const { username } = useWorkspaceContext();
  const memoir = useGenerateMemoir();
  const inFlightRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploadError, setUploadError] = useState<NormalizedApiError | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  const { register, handleSubmit } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      target_length: 2000,
      user_preferences: "温暖、克制、重视家庭细节"
    }
  });

  const onMemoirSubmit = handleSubmit(async (values) => {
    await memoir.mutateAsync({
      username: username ?? "",
      target_length: values.target_length,
      user_preferences: values.user_preferences,
      auto_save: true
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

  const handleKnowledgeUpload = async (file: File | null) => {
    if (!file || !username) return;
    setUploadError(null);
    setUploadSuccess(null);
    try {
      const result = await processKnowledgeFile(username, file);
      setUploadSuccess(`上传完成：${result.original_filename}`);
    } catch (error) {
      setUploadError(normalizeUnknownError(error, "上传失败"));
    }
  };

  return (
    <div
      className="min-h-screen"
      style={{ background: "radial-gradient(circle at top, #FDF6EE 0%, #fafaf8 45%, #fafaf8 100%)" }}
    >
      <main className="mx-auto max-w-2xl px-6 py-8">
        {/* Inline parameter bar */}
        <form onSubmit={onFormSubmit}>
          <div className="flex flex-wrap items-end gap-4 pb-5 border-b border-black/[0.08]">
            <label className="flex flex-col gap-1 min-w-[120px]">
              <span className="text-xs uppercase tracking-[0.16em] text-slate-400">目标字数</span>
              <Input aria-label="目标字数" type="number" {...register("target_length")} className="w-28" />
            </label>
            <label className="flex flex-col gap-1 flex-1 min-w-[200px]">
              <span className="text-xs uppercase tracking-[0.16em] text-slate-400">叙事偏好</span>
              <Input aria-label="叙事偏好" {...register("user_preferences")} />
            </label>
            <div className="flex items-center gap-2 pb-0.5">
              <Button type="submit" disabled={memoir.isPending || !username} aria-label="生成回忆录">
                <Sparkles className="mr-2 h-4 w-4" />
                {memoir.isPending ? "生成中" : "生成回忆录"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={!username}
                onClick={() => fileInputRef.current?.click()}
                aria-label="上传知识素材"
              >
                <UploadCloud className="mr-2 h-4 w-4" />
                上传素材
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.markdown,text/plain"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  void handleKnowledgeUpload(file);
                  e.currentTarget.value = "";
                }}
              />
            </div>
          </div>
        </form>

        {/* Upload feedback */}
        {uploadSuccess && (
          <p className="mt-3 text-sm text-emerald-700">{uploadSuccess}</p>
        )}
        {uploadError && (
          <div className="mt-3">
            <ErrorBanner
              code={uploadError.code}
              message={uploadError.message}
              retryable={false}
            />
          </div>
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
              onRetry={memoir.canRetry ? () => void onMemoirSubmit() : undefined}
            />
          </div>
        )}

        {/* Memoir body */}
        <div className="mt-8">
          {memoir.data ? (
            <>
              <article className="memoir-prose text-slate-800">
                <p>{memoir.data.memoir}</p>
              </article>
              <p className="mt-8 text-xs text-slate-400">
                字数：{memoir.data.length}
                {memoir.data.generated_at ? ` · 生成于 ${memoir.data.generated_at.slice(0, 10)}` : ""}
                {memoir.data.trace_id ? ` · Trace: ${memoir.data.trace_id}` : ""}
              </p>
            </>
          ) : (
            <p className="text-slate-400">尚未生成内容。请先上传素材（可选）并点击"生成回忆录"。</p>
          )}
        </div>
      </main>
    </div>
  );
}
