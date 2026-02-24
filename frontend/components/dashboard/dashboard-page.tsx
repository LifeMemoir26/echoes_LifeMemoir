"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { motion } from "framer-motion";
import { BookOpen, CalendarDays, Library, MessageSquare, Upload } from "lucide-react";
import { UploadMaterialModal } from "@/components/knowledge/upload-material-modal";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { MagneticHover } from "@/components/ui/magnetic-hover";
import { softSpring, smooth } from "@/lib/motion/spring";

const FEATURE_CARDS = [
  {
    href: "/interview",
    icon: MessageSquare,
    title: "采访",
    description: "开始一次生命故事采访"
  },
  {
    href: "/memoir",
    icon: BookOpen,
    title: "回忆录",
    description: "生成完整的生命回忆录"
  },
  {
    href: "/timeline",
    icon: CalendarDays,
    title: "时间线",
    description: "生成按时间排列的事件时间线"
  },
  {
    href: "/knowledge",
    icon: Library,
    title: "知识库",
    description: "查看采访记录与提取的人生事件"
  }
];

export function DashboardPage() {
  const { username } = useWorkspaceContext();
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-12">
        {/* Page heading */}
        <motion.div
          className="mb-8"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={smooth}
        >
          <h1 className="font-[var(--font-heading)] text-3xl text-slate-900">
            欢迎回来{username ? `，${username}` : ""}
          </h1>
          <p className="mt-1 text-sm text-slate-500">选择一个功能开始你的回忆之旅</p>
        </motion.div>
        <div className="grid gap-6 md:grid-cols-2">
          {FEATURE_CARDS.map(({ href, icon: Icon, title, description }, index) => {
            const isKnowledge = href === "/knowledge";
            return (
              <motion.div
                key={href}
                className="relative"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...softSpring, delay: 0.08 + index * 0.06 }}
              >
                <MagneticHover>
                  <Link
                    href={href as Route}
                    className="group block cursor-pointer rounded-2xl border border-black/[0.06] bg-white/80 p-8 backdrop-blur-[15px] backdrop-saturate-[1.8] shadow-[var(--shadow-card)] transition-all duration-200 hover:shadow-[var(--shadow-card-hover)] hover:border-[#C4A882] hover:-translate-y-px"
                  >
                    <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-3 transition-transform duration-200 group-hover:scale-110">
                      <Icon className="h-6 w-6 text-[#A2845E]" aria-hidden="true" />
                    </div>
                    <h2 className="font-[var(--font-heading)] text-2xl text-slate-900">{title}</h2>
                    <p className="mt-1 text-sm text-slate-500">{description}</p>
                    {isKnowledge && (
                      <div className="mt-4">
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setUploadModalOpen(true);
                          }}
                          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-[#C4A882]/40 bg-[#F5EDE4] px-3 py-1.5 text-xs text-[#A2845E] transition hover:border-[#A2845E]"
                        >
                          <Upload className="h-3 w-3" />
                          上传资料 +
                        </button>
                      </div>
                    )}
                  </Link>
                </MagneticHover>
              </motion.div>
            );
          })}
        </div>
      </main>

      {username && (
        <UploadMaterialModal
          open={uploadModalOpen}
          onClose={() => setUploadModalOpen(false)}
          username={username}
        />
      )}
    </div>
  );
}
