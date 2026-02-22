"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { register } from "@/lib/api/auth";
import { normalizeUnknownError } from "@/lib/api/client";

export function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(username.trim(), password);
      router.replace("/login");
    } catch (err) {
      const normalized = normalizeUnknownError(err, "注册失败，请重试");
      setError(normalized.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{
        background: "radial-gradient(circle at top, #FDF6EE 0%, #fafaf8 45%, #fafaf8 100%)"
      }}
    >
      <div className="mx-auto flex h-16 max-w-2xl w-full items-center px-6">
        <span className="font-[var(--font-heading)] text-xl text-[#A2845E]">ECHOES</span>
      </div>

      <main className="mx-auto w-full max-w-sm flex-1 px-6 py-8">
        <h1 className="mb-8 font-[var(--font-heading)] text-2xl text-slate-900">注册</h1>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-[0.16em] text-[#A2845E]" htmlFor="reg-username">
              用户名
            </label>
            <Input
              id="reg-username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="alice"
            />
            <p className="text-xs text-slate-400">仅限字母、数字、下划线、连字符（1–128 位）</p>
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-[0.16em] text-[#A2845E]" htmlFor="reg-password">
              密码
            </label>
            <Input
              id="reg-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 8 位"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "注册中…" : "创建账号"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500">
          已有账号？{" "}
          <Link href="/login" className="text-[#A2845E] hover:underline">
            登录
          </Link>
        </p>
      </main>
    </div>
  );
}
