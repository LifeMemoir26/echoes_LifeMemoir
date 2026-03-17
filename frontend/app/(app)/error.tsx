"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("App route crashed", error);
  }, [error]);

  return (
    <main className="flex min-h-dvh items-center justify-center bg-[#F7F1E8] px-6">
      <div className="w-full max-w-xl rounded-3xl border border-[#A2845E]/15 bg-white/85 p-8 text-center shadow-[0_24px_80px_rgba(86,60,28,0.08)] backdrop-blur-sm">
        <p className="font-[var(--font-display)] text-sm uppercase tracking-[0.22em] text-[#A2845E]/70">
          Echoes
        </p>
        <h1 className="mt-4 font-[var(--font-heading)] text-3xl text-[#6B523A]">
          页面刚才出了点问题
        </h1>
        <p className="mt-3 text-base leading-7 text-slate-600">
          我们已经拦住了这次前端异常。你可以先重新加载当前页面，如果还会复现，我会继续按时间戳追查。
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Button onClick={reset}>重试当前页面</Button>
          <Button variant="ghost" onClick={() => window.location.reload()}>
            整页刷新
          </Button>
        </div>
      </div>
    </main>
  );
}
