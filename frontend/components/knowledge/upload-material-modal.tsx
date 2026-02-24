"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { Input } from "@/components/ui/input";
import { uploadMaterial, type MaterialUploadItem } from "@/lib/api/knowledge-browser";

interface Props {
  open: boolean;
  onClose: () => void;
  username: string;
}

export function UploadMaterialModal({ open, onClose, username }: Props) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [displayName, setDisplayName] = useState("");
  const [materialContext, setMaterialContext] = useState("");
  const [skipProcessing, setSkipProcessing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState<MaterialUploadItem[] | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);

  if (!open) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    setSelectedFiles((prev) => [...prev, ...files]);
    e.target.value = "";
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!selectedFiles.length) return;
    setSubmitting(true);
    setGlobalError(null);
    setResults(null);
    try {
      const data = await uploadMaterial(username, selectedFiles, materialContext, displayName.trim(), skipProcessing);
      setResults(data.items);
      void queryClient.invalidateQueries({ queryKey: ["materials"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["records"] });
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    setSelectedFiles([]);
    setDisplayName("");
    setMaterialContext("");
    setSkipProcessing(false);
    setResults(null);
    setGlobalError(null);
    onClose();
  };

  const allDone = results !== null;
  const canSubmit = selectedFiles.length > 0 && displayName.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-black/[0.06] bg-white p-6 shadow-xl">
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">上传资料</h2>
          <button
            onClick={handleClose}
            className="cursor-pointer rounded-lg p-1 text-slate-400 hover:text-slate-600"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {!allDone ? (
          <>
            {/* Display name (required) */}
            <div className="mb-4">
              <p className="mb-2 text-xs uppercase tracking-[0.16em] text-[#A2845E]">
                存储文件名<span className="ml-1 normal-case text-rose-400">必填</span>
              </p>
              <Input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                disabled={submitting}
                placeholder="例：2023年日记、高中回忆录"
              />
            </div>

            {/* File selection */}
            <div className="mb-4">
              <p className="mb-2 text-xs uppercase tracking-[0.16em] text-[#A2845E]">选择文件</p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".txt,.md,.markdown,text/*"
                className="hidden"
                onChange={handleFileChange}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={submitting}
              >
                <Upload className="mr-1.5 h-3.5 w-3.5" />
                选择文件（可多选）
              </Button>
              {selectedFiles.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {selectedFiles.map((f, i) => (
                    <li
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-[#F5EDE4] px-3 py-1.5 text-sm text-slate-700"
                    >
                      <span className="truncate">{f.name}</span>
                      <button
                        onClick={() => removeFile(i)}
                        className="ml-2 flex-shrink-0 cursor-pointer text-slate-400 hover:text-rose-500"
                        aria-label={`移除 ${f.name}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Context textarea */}
            <div className="mb-4">
              <p className="mb-2 text-xs uppercase tracking-[0.16em] text-[#A2845E]">背景说明（可选）</p>
              <textarea
                value={materialContext}
                onChange={(e) => setMaterialContext(e.target.value)}
                disabled={submitting}
                placeholder='文中的"XX"指的是我，写于...年代...'
                rows={3}
                className="focus-visible-ring w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 disabled:opacity-50"
              />
            </div>

            {/* Skip processing checkbox */}
            <label className="mb-5 flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={skipProcessing}
                onChange={(e) => setSkipProcessing(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 rounded border-[#C4A882]/40 text-[#A2845E] accent-[#A2845E]"
              />
              <span className="text-sm text-slate-600">
                稍后处理
                <span className="ml-1 text-xs text-slate-400">（仅保存文件，之后在知识库页面手动结构化）</span>
              </span>
            </label>

            {globalError && (
              <p className="mb-4 text-sm text-rose-600">{globalError}</p>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={handleClose} disabled={submitting}>
                取消
              </Button>
              <Button
                size="sm"
                onClick={handleSubmit}
                disabled={submitting || !canSubmit}
              >
                {submitting ? "处理中…" : skipProcessing ? "仅上传" : "开始处理"}
              </Button>
            </div>
          </>
        ) : (
          <>
            {/* Results */}
            <div className="mb-5 space-y-2">
              {results.map((item, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-xl border border-black/[0.06] bg-white/80 p-3"
                >
                  <span className="truncate text-sm text-slate-700">{item.file_name}</span>
                  <div className="ml-3 flex-shrink-0">
                    <StatusBadge
                      status={item.status === "success" ? "success" : "error"}
                      label={
                        item.status === "success"
                          ? `提取 ${item.events_count} 事件`
                          : (item.error_message ?? "失败")
                      }
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <Button size="sm" onClick={handleClose}>
                完成
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
