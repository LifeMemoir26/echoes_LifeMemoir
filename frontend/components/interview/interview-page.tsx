"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { RefreshCw, Send, X } from "lucide-react";
import { useInterviewEvents } from "@/lib/hooks/use-interview-events";
import { useInterviewSession } from "@/lib/hooks/use-interview-session";
import { useWorkspaceContext } from "@/lib/workspace/context";
import type { EventSupplementItem, PendingEventDetail } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { BackgroundSupplementPanel } from "./background-supplement-panel";
import { EmotionalAnchorsPanel } from "./emotional-anchors-panel";
import { PendingEventsPanel } from "./pending-events-panel";

type Message = { role: "user"; content: string; at: string };

export function InterviewPage() {
  const { session, state, error, canSubmitCommand, create, send, flush, close, syncFromServerEvent } =
    useInterviewSession();

  const { username } = useWorkspaceContext();
  const { contextEvent, statusEvent, completedEvent } = useInterviewEvents(session?.session_id ?? null);

  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [supplements, setSupplements] = useState<EventSupplementItem[]>([]);
  const [pendingEvents, setPendingEvents] = useState<PendingEventDetail[]>([]);
  const [positiveTriggers, setPositiveTriggers] = useState<string[]>([]);
  const [sensitiveTopics, setSensitiveTopics] = useState<string[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (statusEvent) syncFromServerEvent(statusEvent.status, statusEvent.session_id);
  }, [statusEvent, syncFromServerEvent]);

  useEffect(() => {
    if (completedEvent) syncFromServerEvent(completedEvent.status, completedEvent.session_id);
  }, [completedEvent, syncFromServerEvent]);

  useEffect(() => {
    if (!contextEvent) return;

    setSupplements(contextEvent.event_supplements ?? []);
    setPositiveTriggers(contextEvent.positive_triggers ?? []);
    setSensitiveTopics(contextEvent.sensitive_topics ?? []);

    const events = contextEvent.pending_events?.events ?? [];
    setPendingEvents(events);

    const incomingIds = new Set(events.map((e) => e.id));
    setExpandedIds((prev) => {
      const pruned = new Set<string>();
      prev.forEach((id) => {
        if (incomingIds.has(id)) pruned.add(id);
      });
      return pruned;
    });
  }, [contextEvent]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, state]);

  const handleCreate = useCallback(async () => {
    if (!username) return;
    await create(username);
  }, [create, username]);

  const handleSend = useCallback(async () => {
    const content = draft.trim();
    if (!content || !canSubmitCommand) return;
    setDraft("");
    setMessages((prev) => [...prev, { role: "user", content, at: new Date().toISOString() }]);
    await send(content);
  }, [canSubmitCommand, draft, send]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend]
  );

  const handleToggle = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const isConnected = session !== null && state !== "closed" && state !== "idle_timeout";
  const isProcessing = state === "processing" || state === "flushing";

  const statusLabel = isProcessing
    ? { status: "loading" as const, text: "处理中" }
    : isConnected
      ? { status: "success" as const, text: "已连接" }
      : error
        ? { status: "error" as const, text: "有错误" }
        : { status: "idle" as const, text: "未开始" };

  return (
    <main
      className="flex min-h-screen flex-col"
      style={{ background: "radial-gradient(circle at top, #FDF6EE 0%, #fafaf8 45%, #fafaf8 100%)" }}
    >
      {/* Status bar */}
      <div className="shrink-0 flex items-center justify-end px-6 py-3 border-b border-black/[0.06] bg-white/80 backdrop-blur-sm">
        <StatusBadge status={statusLabel.status} label={statusLabel.text} />
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* LEFT: conversation area */}
        <div className="flex w-[420px] shrink-0 flex-col border-r border-slate-200/70 bg-white">
          {/* sub-header */}
          <div className="shrink-0 border-b border-slate-200 px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-500">
                {session ? `采访对象 · ${session.username}` : "对话区"}
              </p>
              {isConnected && (
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void flush()}
                    disabled={!canSubmitCommand}
                    title="刷新上下文"
                    aria-label="刷新上下文"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void close()}
                    className="text-rose-500 hover:bg-rose-50 hover:text-rose-700"
                    title="关闭会话"
                    aria-label="关闭会话"
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </div>
          </div>

          {!isConnected && state !== "creating_session" && (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6">
              <p className="text-center text-sm text-slate-500">
                {state === "closed" || state === "idle_timeout"
                  ? "会话已结束，请重新创建"
                  : "为当前账户开始一次采访"}
              </p>
              {error && (
                <p className="text-center text-xs text-rose-600">{error.message}</p>
              )}
              <div className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                {username || "—"}
              </div>
              <Button
                onClick={() => void handleCreate()}
                disabled={!username}
                className="w-full"
              >
                创建会话
              </Button>
            </div>
          )}

          {state === "creating_session" && (
            <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
              正在创建会话…
            </div>
          )}

          {isConnected && (
            <>
              <div className="flex-1 overflow-y-auto space-y-3 px-4 py-4">
                {messages.length === 0 && (
                  <p className="pt-8 text-center text-xs text-slate-400">
                    发送第一条采访内容开始记录
                  </p>
                )}
                {messages.map((msg, i) => (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-[#A2845E] px-3 py-2 text-sm leading-relaxed text-white">
                      {msg.content}
                    </div>
                  </div>
                ))}
                {isProcessing && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl rounded-tl-sm bg-slate-100 px-3 py-2 text-xs text-slate-500">
                      {state === "flushing" ? "正在刷新上下文…" : "处理中…"}
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className="shrink-0 border-t border-slate-200 p-3">
                <div className="flex gap-2">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={2}
                    disabled={!canSubmitCommand}
                    placeholder="输入采访内容… (Enter 发送)"
                    aria-label="采访内容输入"
                    className="focus-visible-ring flex-1 resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 disabled:opacity-50"
                  />
                  <Button
                    onClick={() => void handleSend()}
                    disabled={!canSubmitCommand || !draft.trim()}
                    size="sm"
                    className="self-end"
                    aria-label="发送消息"
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* RIGHT: three-panel assist area */}
        <div className="grid flex-1 grid-cols-2 grid-rows-2 gap-4 overflow-hidden p-6">
          <div className="row-span-2 overflow-hidden rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-5">
            <BackgroundSupplementPanel supplements={supplements} />
          </div>

          <div className="overflow-hidden rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-5">
            <PendingEventsPanel events={pendingEvents} expandedIds={expandedIds} onToggle={handleToggle} />
          </div>

          <div className="overflow-hidden rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur-sm p-5">
            <EmotionalAnchorsPanel positiveTriggers={positiveTriggers} sensitiveTopics={sensitiveTopics} />
          </div>
        </div>
      </div>
    </main>
  );
}
