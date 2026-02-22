"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { BookOpen, CalendarDays, Library, MessageSquare, Upload } from "lucide-react";
import { UploadMaterialModal } from "@/components/knowledge/upload-material-modal";
import { useWorkspaceContext } from "@/lib/workspace/context";

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
    <div
      className="flex min-h-screen flex-col"
      style={{
        background: "radial-gradient(circle at top, #FDF6EE 0%, #fafaf8 45%, #fafaf8 100%)"
      }}
    >
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-12">
        <div className="grid gap-6 md:grid-cols-2">
          {FEATURE_CARDS.map(({ href, icon: Icon, title, description }) => {
            const isKnowledge = href === "/knowledge";
            return (
              <div key={href} className="relative">
                <Link
                  href={href as Route}
                  className="group block cursor-pointer rounded-2xl border border-black/[0.06] bg-white/80 p-8 backdrop-blur-sm transition duration-200 hover:border-[#C4A882]"
                >
                  <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-3">
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
              </div>
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
