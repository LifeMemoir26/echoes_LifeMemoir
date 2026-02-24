"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronUp, FileText, Trash2, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { useKnowledgeEvents, useKnowledgeProfiles, useKnowledgeMaterials, useKnowledgeMaterialContent } from "@/lib/hooks/use-knowledge-events";
import { useKnowledgeStructuring } from "@/lib/hooks/use-knowledge-structuring";
import { deleteMaterial } from "@/lib/api/knowledge-browser";
import { UploadMaterialModal } from "@/components/knowledge/upload-material-modal";
import type { EventItem, MaterialItem } from "@/lib/api/knowledge-browser";

type Tab = "files" | "events";

const STAGE_ORDER = ["读取文件", "提取事件", "向量化", "完成"] as const;

function StructuringProgress({ stage }: { stage: string | null }) {
  const current = STAGE_ORDER.indexOf(stage as typeof STAGE_ORDER[number]);
  return (
    <div className="flex items-center gap-1.5 mt-2">
      {STAGE_ORDER.map((s, i) => (
        <div key={s} className="flex items-center gap-1.5">
          <div
            className={`h-1.5 w-1.5 rounded-full transition-colors duration-300 ${
              i < current
                ? "bg-[#A2845E]"
                : i === current
                ? "animate-pulse bg-[#A2845E]"
                : "bg-slate-200"
            }`}
          />
          <span className={`text-xs ${i === current ? "text-[#A2845E] font-medium" : "text-slate-400"}`}>
            {s}
          </span>
          {i < STAGE_ORDER.length - 1 && <span className="text-slate-200 text-xs">›</span>}
        </div>
      ))}
    </div>
  );
}

function FileCard({ item }: { item: MaterialItem }) {
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const queryClient = useQueryClient();
  const contentQuery = useKnowledgeMaterialContent(expanded ? item.id : null);
  const { isProcessing, stage, error: structuringError, trigger, cancel } = useKnowledgeStructuring(item.id);
  const label = item.display_name || item.filename;

  // Derive display status: local processing state overrides DB status
  const effectiveStatus = isProcessing ? "processing" : item.status;

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteMaterial(item.id);
      void queryClient.invalidateQueries({ queryKey: ["materials"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
    } catch {
      // silently fail — user can retry
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <motion.div layout className="rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-[#A2845E]" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-700">{label}</p>
            <p className="mt-0.5 text-xs text-slate-400">
              存档于 {item.uploaded_at.slice(0, 10)}
            </p>
            {/* Structuring progress bar */}
            {isProcessing && <StructuringProgress stage={stage} />}
            {/* Structuring error */}
            {structuringError && !isProcessing && (
              <p className="mt-1 text-xs text-rose-500">{structuringError}</p>
            )}
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-2">
          {/* Structuring status badge */}
          {effectiveStatus === "done" && (
            <StatusBadge status="success" label="已结构化" />
          )}
          {effectiveStatus === "processing" && (
            <StatusBadge status="loading" label={stage ?? "处理中"} />
          )}
          {effectiveStatus === "processing" && (
            <button
              onClick={cancel}
              className="cursor-pointer rounded-md px-2 py-0.5 text-xs text-slate-400 hover:text-rose-400"
            >
              取消
            </button>
          )}
          {effectiveStatus === "failed" && !isProcessing && (
            <StatusBadge status="error" label="失败" />
          )}
          {(effectiveStatus === "pending" || effectiveStatus === "failed") && !isProcessing && (
            <Button
              variant="secondary"
              size="sm"
              onClick={trigger}
              className="text-xs"
            >
              结构化
            </Button>
          )}

          <button
            onClick={() => setExpanded((v) => !v)}
            className="cursor-pointer rounded-lg p-1 text-slate-400 hover:text-[#A2845E]"
            aria-label={expanded ? "折叠" : "展开查看原文"}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>

          {/* Delete button */}
          {!confirmDelete ? (
            <button
              onClick={() => setConfirmDelete(true)}
              disabled={isProcessing || deleting}
              className="cursor-pointer rounded-lg p-1 text-slate-300 hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-30"
              aria-label="删除资料"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          ) : (
            <div className="flex items-center gap-1">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-md bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-500 hover:bg-rose-100 disabled:opacity-50"
              >
                {deleting ? "…" : "确认"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
                className="rounded-md px-2 py-0.5 text-xs text-slate-400 hover:text-slate-600"
              >
                取消
              </button>
            </div>
          )}
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            key="file-content"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-4 border-t border-slate-100 pt-4">
              {contentQuery.isLoading && (
                <p className="text-sm text-slate-400">加载中…</p>
              )}
              {contentQuery.isError && (
                <p className="text-sm text-rose-500">无法加载文件内容</p>
              )}
              {contentQuery.data && (
                <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap font-mono text-sm leading-relaxed text-slate-700">
                  {contentQuery.data.content}
                </pre>
              )}
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
            <div className="mt-4 max-h-64 space-y-2 overflow-y-auto border-t border-slate-100 pt-4">
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

export function KnowledgePage() {
  const { username } = useWorkspaceContext();
  const [activeTab, setActiveTab] = useState<Tab>("files");
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  const eventsQuery = useKnowledgeEvents();
  const profilesQuery = useKnowledgeProfiles();
  const materialsQuery = useKnowledgeMaterials();

  return (
    <div className="flex min-h-screen flex-col">
      {/* Tabs */}
      <div className="border-b border-slate-200 bg-white/80">
        <div className="mx-auto flex max-w-3xl gap-0 px-6">
          {[
            { key: "files", label: "资料文件" },
            { key: "events", label: "人生事件 & 侧写" }
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
        {activeTab === "files" && (
          <>
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-400">原始资料</p>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setUploadModalOpen(true)}
              >
                <UploadCloud className="mr-1.5 h-3.5 w-3.5" />
                上传资料
              </Button>
            </div>

            {materialsQuery.isLoading && <p className="text-sm text-slate-400">加载中…</p>}
            {materialsQuery.isError && <p className="text-sm text-rose-600">加载失败，请刷新重试</p>}
            {materialsQuery.data?.materials.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center">
                <p className="text-sm text-slate-400">暂无资料文件</p>
                <p className="mt-1 text-xs text-slate-300">点击右上角「上传资料」添加文件</p>
              </div>
            )}
            {materialsQuery.data?.materials.map((item) => (
              <FileCard key={item.id} item={item} />
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
