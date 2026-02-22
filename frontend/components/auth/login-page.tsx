"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { login } from "@/lib/api/auth";
import { saveToken } from "@/lib/auth/token";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { normalizeUnknownError } from "@/lib/api/client";

export function LoginPage() {
  const router = useRouter();
  const { setToken, setUsername } = useWorkspaceContext();
  const [username, setUsernameField] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await login(username.trim(), password);
      saveToken(data.access_token, data.username);
      setToken(data.access_token);
      setUsername(data.username);
      router.replace("/");
    } catch (err) {
      const normalized = normalizeUnknownError(err, "登录失败，请重试");
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
        <h1 className="mb-8 font-[var(--font-heading)] text-2xl text-slate-900">登录</h1>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-[0.16em] text-[#A2845E]" htmlFor="username">
              用户名
            </label>
            <Input
              id="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsernameField(e.target.value)}
              placeholder="alice"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-[0.16em] text-[#A2845E]" htmlFor="password">
              密码
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "登录中…" : "登录"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500">
          还没有账号？{" "}
          <Link href="/register" className="text-[#A2845E] hover:underline">
            注册
          </Link>
        </p>
      </main>
    </div>
  );
}
