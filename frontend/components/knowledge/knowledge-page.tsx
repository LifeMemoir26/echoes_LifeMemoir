"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronUp, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { useKnowledgeRecords } from "@/lib/hooks/use-knowledge-records";
import { useKnowledgeEvents, useKnowledgeProfiles, useKnowledgeMaterials } from "@/lib/hooks/use-knowledge-events";
import { UploadMaterialModal } from "@/components/knowledge/upload-material-modal";
import type { RecordItem, EventItem, MaterialItem } from "@/lib/api/knowledge-browser";

type Tab = "records" | "events" | "materials";

function materialStatusMap(status: MaterialItem["status"]): "success" | "loading" | "idle" | "error" {
  if (status === "done") return "success";
  if (status === "processing") return "loading";
  if (status === "failed") return "error";
  return "idle";
}

function materialStatusLabel(status: MaterialItem["status"]): string {
  if (status === "done") return "已完成";
  if (status === "processing") return "处理中";
  if (status === "failed") return "失败";
  return "等待中";
}

function RecordCard({ item }: { item: RecordItem }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div layout className="rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">
              采访记录 #{item.chunk_id}
            </span>
            <StatusBadge
              status={item.is_structured ? "success" : "idle"}
              label={item.is_structured ? "已结构化" : "待结构化"}
            />
          </div>
          <p className="line-clamp-2 text-sm text-slate-600">{item.preview}</p>
          <p className="mt-1 text-xs text-slate-400">
            {item.total_chars} 字 · {item.created_at.slice(0, 10)}
          </p>
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex-shrink-0 cursor-pointer rounded-lg p-1 text-slate-400 hover:text-[#A2845E]"
          aria-label={expanded ? "折叠" : "展开"}
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            key="expanded-record"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-4 border-t border-slate-100 pt-4">
              <p className="whitespace-pre-wrap text-sm text-slate-700">{item.preview}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function EventCard({ item }: { item: EventItem }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div layout className="rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-[#A2845E]">{item.year}</span>
            {item.life_stage && item.life_stage !== "未知" && (
              <span className="rounded-full bg-[#F5EDE4] px-2 py-0.5 text-xs text-[#A2845E]">
                {item.life_stage}
              </span>
            )}
            {item.is_merged && (
              <span className="rounded-full bg-[#F5EDE4] px-2 py-0.5 text-xs text-[#A2845E]">
                已合并
              </span>
            )}
          </div>
          <p className="text-sm text-slate-700">{item.event_summary}</p>
          {item.event_category.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {item.event_category.map((cat) => (
                <span
                  key={cat}
                  className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-500"
                >
                  {cat}
                </span>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex-shrink-0 cursor-pointer rounded-lg p-1 text-slate-400 hover:text-[#A2845E]"
          aria-label={expanded ? "折叠" : "展开"}
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            key="expanded-event"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
              {item.time_detail && (
                <p className="text-xs text-slate-400">
                  <span className="font-medium text-slate-600">时间细节：</span>
                  {item.time_detail}
                </p>
              )}
              {item.event_details && (
                <p className="whitespace-pre-wrap text-sm text-slate-700">{item.event_details}</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function MaterialCard({ item }: { item: MaterialItem }) {
  return (
    <div className="rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-700">{item.filename}</p>
          <p className="mt-0.5 text-xs text-slate-400">
            {item.material_type === "interview" ? "采访记录" : "上传文档"} ·{" "}
            {item.events_count} 事件 · {item.uploaded_at.slice(0, 10)}
          </p>
          {item.material_context && (
            <p className="mt-1 line-clamp-2 text-xs italic text-slate-500">{item.material_context}</p>
          )}
        </div>
        <div className="flex-shrink-0">
          <StatusBadge
            status={materialStatusMap(item.status)}
            label={materialStatusLabel(item.status)}
          />
        </div>
      </div>
    </div>
  );
}

export function KnowledgePage() {
  const { username } = useWorkspaceContext();
  const [activeTab, setActiveTab] = useState<Tab>("records");
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  const recordsQuery = useKnowledgeRecords();
  const eventsQuery = useKnowledgeEvents();
  const profilesQuery = useKnowledgeProfiles();
  const materialsQuery = useKnowledgeMaterials();

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{
        background: "radial-gradient(circle at top, #FDF6EE 0%, #fafaf8 45%, #fafaf8 100%)"
      }}
    >
      {/* Tabs */}
      <div className="border-b border-slate-200 bg-white/80">
        <div className="mx-auto flex max-w-3xl gap-0 px-6">
          {[
            { key: "records", label: "采访记录" },
            { key: "events", label: "人生事件 & 侧写" },
            { key: "materials", label: "上传资料" }
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as Tab)}
              className={`cursor-pointer border-b-2 px-4 py-3 text-xs uppercase tracking-[0.16em] transition-colors duration-150 ${
                activeTab === tab.key
                  ? "border-[#A2845E] text-[#A2845E]"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-6 py-8">
        {activeTab === "records" && (
          <>
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-400">背景材料</p>
            </div>

            {recordsQuery.isLoading && <p className="text-sm text-slate-400">加载中…</p>}
            {recordsQuery.isError && <p className="text-sm text-rose-600">加载失败，请刷新重试</p>}
            {recordsQuery.data?.records.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center">
                <p className="text-sm text-slate-400">暂无采访记录</p>
                <p className="mt-1 text-xs text-slate-300">完成一次采访后，记录会出现在这里</p>
              </div>
            )}
            {recordsQuery.data?.records.map((item) => (
              <RecordCard key={item.chunk_id} item={item} />
            ))}
          </>
        )}

        {activeTab === "events" && (
          <>
            {eventsQuery.isLoading && <p className="text-sm text-slate-400">加载中…</p>}
            {eventsQuery.data?.events.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center">
                <p className="text-sm text-slate-400">暂无人生事件</p>
              </div>
            )}
            {eventsQuery.data?.events.map((item) => (
              <EventCard key={item.id} item={item} />
            ))}

            {profilesQuery.data && (profilesQuery.data.personality || profilesQuery.data.worldview) && (
              <div className="mt-6 rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-6">
                <p className="mb-4 text-xs uppercase tracking-[0.16em] text-[#A2845E]">
                  人物侧写
                </p>
                {profilesQuery.data.personality && (
                  <div className="mb-4">
                    <p className="mb-1 text-xs font-semibold text-slate-600">性格特征</p>
                    <p className="whitespace-pre-wrap text-sm text-slate-700">
                      {profilesQuery.data.personality}
                    </p>
                  </div>
                )}
                {profilesQuery.data.worldview && (
                  <div>
                    <p className="mb-1 text-xs font-semibold text-slate-600">世界观 / 价值观</p>
                    <p className="whitespace-pre-wrap text-sm text-slate-700">
                      {profilesQuery.data.worldview}
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {activeTab === "materials" && (
          <>
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-400">已上传资料</p>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setUploadModalOpen(true)}
              >
                <Upload className="mr-1.5 h-3.5 w-3.5" />
                上传资料
              </Button>
            </div>

            {materialsQuery.isLoading && <p className="text-sm text-slate-400">加载中…</p>}
            {materialsQuery.isError && <p className="text-sm text-rose-600">加载失败，请刷新重试</p>}
            {materialsQuery.data?.materials.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center">
                <p className="text-sm text-slate-400">暂无上传资料</p>
                <p className="mt-1 text-xs text-slate-300">
                  上传日记、文章等文档，AI 将自动提取人生事件
                </p>
              </div>
            )}
            {materialsQuery.data?.materials.map((item) => (
              <MaterialCard key={item.id} item={item} />
            ))}
          </>
        )}
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
