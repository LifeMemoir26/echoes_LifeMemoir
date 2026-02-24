"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronUp, FileText, FolderOpen, Mic, Trash2, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { useKnowledgeMaterials, useKnowledgeMaterialContent } from "@/lib/hooks/use-knowledge-events";
import { useKnowledgeStructuring } from "@/lib/hooks/use-knowledge-structuring";
import { deleteMaterial } from "@/lib/api/knowledge-browser";
import { UploadMaterialModal } from "@/components/knowledge/upload-material-modal";
import type { MaterialItem } from "@/lib/api/knowledge-browser";
import { softSpring } from "@/lib/motion/spring";

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

function FileCard({ item, index }: { item: MaterialItem; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const queryClient = useQueryClient();
  const contentQuery = useKnowledgeMaterialContent(expanded ? item.id : null);
  const { isProcessing, stage, error: structuringError, trigger, cancel } = useKnowledgeStructuring(item.id);
  const label = item.display_name || item.filename;

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
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...softSpring, delay: index * 0.04 }}
      className="rounded-xl border border-black/[0.06] bg-white/80 p-5 shadow-[var(--shadow-card)] backdrop-blur-sm transition-shadow duration-200 hover:shadow-[var(--shadow-card-hover)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          {item.material_type === "interview" ? (
            <Mic className="mt-0.5 h-4 w-4 flex-shrink-0 text-[#A2845E]" />
          ) : (
            <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-[#A2845E]" />
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-700">{label}</p>
            <p className="mt-0.5 text-xs text-slate-400">
              存档于 {item.uploaded_at.slice(0, 10)}
            </p>
            {isProcessing && <StructuringProgress stage={stage} />}
            {structuringError && !isProcessing && (
              <p className="mt-1 text-xs text-rose-500">{structuringError}</p>
            )}
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-2">
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
            className="cursor-pointer rounded-lg p-1.5 text-[#C4A882] transition-colors duration-150 hover:text-[#A2845E] hover:bg-[#F5EDE4]/50"
            aria-label={expanded ? "折叠" : "展开查看原文"}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>

          {!confirmDelete ? (
            <button
              onClick={() => setConfirmDelete(true)}
              disabled={isProcessing || deleting}
              className="cursor-pointer rounded-lg p-1.5 text-slate-300 transition-colors duration-150 hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-30"
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
            <div className="mt-4 border-t border-black/[0.06] pt-4">
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

export function KnowledgePage() {
  const { username } = useWorkspaceContext();
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const materialsQuery = useKnowledgeMaterials();

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-3xl px-6 py-8">
        {/* Page heading */}
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h1 className="font-[var(--font-heading)] text-3xl text-slate-900">
              资料文件
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              上传和管理采访记录与文档
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setUploadModalOpen(true)}
          >
            <UploadCloud className="mr-1.5 h-3.5 w-3.5" />
            上传资料
          </Button>
        </div>

        {/* Material list */}
        <div className="space-y-4">
          {materialsQuery.isLoading && (
            <p className="py-8 text-center text-sm text-slate-400">加载中…</p>
          )}
          {materialsQuery.isError && (
            <p className="py-8 text-center text-sm text-rose-500">加载失败，请刷新重试</p>
          )}
          {materialsQuery.data?.materials.length === 0 && (
            <motion.div
              className="flex flex-col items-center justify-center py-16 text-center"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={softSpring}
            >
              <div className="mb-4 inline-flex rounded-xl bg-[#F5EDE4] p-4">
                <FolderOpen className="h-8 w-8 text-[#C4A882] opacity-60" />
              </div>
              <p className="text-sm italic text-slate-500">暂无资料文件</p>
              <p className="mt-1 text-xs text-slate-400">
                点击右上角「上传资料」添加采访录音或文档
              </p>
            </motion.div>
          )}
          {materialsQuery.data?.materials.map((item, index) => (
            <FileCard key={item.id} item={item} index={index} />
          ))}
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
