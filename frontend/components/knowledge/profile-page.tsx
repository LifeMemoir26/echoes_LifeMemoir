"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { Compass, User } from "lucide-react";
import { useKnowledgeProfiles } from "@/lib/hooks/use-knowledge-events";
import { smooth, softSpring } from "@/lib/motion/spring";

function splitProfileBlocks(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
}

function ProfileBody({ text }: { text: string }) {
  return (
    <div className="profile-prose">
      {splitProfileBlocks(text).map((block, index) =>
        block === "✦" ? (
          <div key={`divider-${index}`} className="ornament-divider my-5">
            <span className="font-[var(--font-display)] text-sm text-[#C4A882]">
              ✦
            </span>
          </div>
        ) : (
          <p key={`paragraph-${index}`}>{block}</p>
        )
      )}
    </div>
  );
}

function ProfileSection({
  title,
  subtitle,
  icon,
  text,
}: {
  title: string;
  subtitle: string;
  icon: ReactNode;
  text: string;
}) {
  return (
    <section className="relative overflow-hidden rounded-[28px] border border-[#E8DDD0] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(249,245,239,0.92))] px-6 py-6 shadow-[0_24px_70px_rgba(120,90,60,0.12)] sm:px-8 sm:py-8">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-[#F5EDE4] blur-2xl"
      />
      <div className="relative flex items-start gap-3">
        <div className="inline-flex rounded-2xl border border-[#E8DDD0] bg-white/90 p-2 shadow-[0_8px_22px_rgba(162,132,94,0.10)]">
          {icon}
        </div>
        <div>
          <p className="panel-label">{title}</p>
          <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
        </div>
      </div>
      <div className="relative mt-5 rounded-[22px] border border-white/80 bg-white/75 px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] sm:px-6 sm:py-6">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute right-4 top-2 font-[var(--font-display)] text-6xl leading-none text-[#E9D8C5]"
        >
          "
        </span>
        <ProfileBody text={text} />
      </div>
    </section>
  );
}

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
            <div className="space-y-5">
              {profilesQuery.data!.personality && (
                <ProfileSection
                  title="性格特征"
                  subtitle="从行为方式与情绪节律中提炼出的气质画像"
                  icon={<User className="h-4 w-4 text-[#A2845E]" />}
                  text={profilesQuery.data!.personality}
                />
              )}

              {profilesQuery.data!.personality &&
                profilesQuery.data!.worldview && (
                  <div className="ornament-divider px-3">
                    <span className="font-[var(--font-display)] text-base text-[#C4A882]">
                      ✦
                    </span>
                  </div>
                )}

              {profilesQuery.data!.worldview && (
                <ProfileSection
                  title="世界观 / 价值观"
                  subtitle="从日常选择与关系感受中沉淀出的信念结构"
                  icon={<Compass className="h-4 w-4 text-[#A2845E]" />}
                  text={profilesQuery.data!.worldview}
                />
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
