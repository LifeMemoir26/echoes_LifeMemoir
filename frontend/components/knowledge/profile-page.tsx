"use client";

import { motion } from "framer-motion";
import { User } from "lucide-react";
import { useKnowledgeProfiles } from "@/lib/hooks/use-knowledge-events";
import { smooth, softSpring } from "@/lib/motion/spring";

export function ProfilePage() {
  const profilesQuery = useKnowledgeProfiles();
  const hasData =
    profilesQuery.data &&
    (profilesQuery.data.personality || profilesQuery.data.worldview);

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-2xl px-6 py-8">
        {/* Page heading */}
        <div className="mb-6">
          <h1 className="font-[var(--font-heading)] text-3xl text-slate-900">
            人物侧写
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            从采访与资料中提取的性格画像
          </p>
        </div>

        {/* Loading */}
        {profilesQuery.isLoading && (
          <p className="py-8 text-center text-sm text-slate-400">加载中…</p>
        )}

        {/* Error */}
        {profilesQuery.isError && (
          <p className="py-8 text-center text-sm text-rose-500">
            加载失败，请刷新重试
          </p>
        )}

        {/* Profile card */}
        {hasData && (
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={smooth}
          >
            <div className="rounded-2xl border border-black/[0.06] bg-white/90 px-8 py-10 shadow-[var(--shadow-perfect)] backdrop-blur-[10px] sm:px-10">
              {/* Personality section */}
              {profilesQuery.data!.personality && (
                <div className="mb-8">
                  <div className="mb-3 flex items-center gap-2">
                    <div className="inline-flex rounded-lg bg-[#F5EDE4] p-1.5">
                      <User className="h-3.5 w-3.5 text-[#A2845E]" />
                    </div>
                    <p className="panel-label">性格特征</p>
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                    {profilesQuery.data!.personality}
                  </p>
                </div>
              )}

              {/* Divider */}
              {profilesQuery.data!.personality &&
                profilesQuery.data!.worldview && (
                  <div className="ornament-divider my-6">
                    <span className="font-[var(--font-display)] text-sm text-[#C4A882]">
                      ✦
                    </span>
                  </div>
                )}

              {/* Worldview section */}
              {profilesQuery.data!.worldview && (
                <div>
                  <div className="mb-3 flex items-center gap-2">
                    <div className="inline-flex rounded-lg bg-[#F5EDE4] p-1.5">
                      <svg
                        className="h-3.5 w-3.5 text-[#A2845E]"
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={1.5}
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418"
                        />
                      </svg>
                    </div>
                    <p className="panel-label">世界观 / 价值观</p>
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                    {profilesQuery.data!.worldview}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* Empty state */}
        {!profilesQuery.isLoading && !hasData && (
          <motion.div
            className="flex flex-col items-center justify-center py-16 text-center"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={softSpring}
          >
            <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-4">
              <User className="h-8 w-8 text-[#C4A882] opacity-60" />
            </div>
            <p className="text-sm italic text-slate-500">暂无人物侧写</p>
            <p className="mt-1 text-xs text-slate-400">
              通过采访互动后，AI 将自动构建人物画像
            </p>
          </motion.div>
        )}
      </main>
    </div>
  );
}
