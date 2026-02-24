"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import { useInterviewEvents } from "@/lib/hooks/use-interview-events";
import { useInterviewSession } from "@/lib/hooks/use-interview-session";
import { useWorkspaceContext } from "@/lib/workspace/context";
import type { EventSupplementItem, PendingEventDetail } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { BackgroundSupplementPanel } from "./background-supplement-panel";
import { EmotionalAnchorsPanel } from "./emotional-anchors-panel";
import { PendingEventsPanel } from "./pending-events-panel";
import { VoiceRecordPanel } from "./voice-record-panel";

type SpeakerRole = "interviewer" | "interviewee";
type Message = { role: SpeakerRole; content: string; at: string };

/** Group consecutive same-speaker messages into merged entries for display. */
function mergeConsecutiveMessages(msgs: Message[]): Array<{ role: SpeakerRole; content: string; at: string; count: number }> {
  const result: Array<{ role: SpeakerRole; content: string; at: string; count: number }> = [];
  for (const msg of msgs) {
    const last = result[result.length - 1];
    if (last && last.role === msg.role) {
      last.content += msg.content;
      last.count += 1;
    } else {
      result.push({ ...msg, count: 1 });
    }
  }
  return result;
}

export function InterviewPage() {
  const { session, state, error, canSubmitCommand, create, send, flush, close, syncFromServerEvent, recoverableSessionId, recoverFromConflict } =
    useInterviewSession();

  const { username, activeSessionId, interviewMessagesCache, setInterviewMessagesCache } = useWorkspaceContext();
  const { contextEvent, statusEvent, completedEvent, connectionState } = useInterviewEvents(session?.session_id ?? null);

  // Restore messages from cache if the session matches and cache is fresh (10 min)
  const messagesCacheAppliedRef = useRef(false);
  const [messages, setMessages] = useState<Message[]>(() => {
    if (
      interviewMessagesCache &&
      activeSessionId &&
      interviewMessagesCache.sessionId === activeSessionId &&
      Date.now() - interviewMessagesCache.savedAt < 10 * 60 * 1000
    ) {
      messagesCacheAppliedRef.current = true;
      return interviewMessagesCache.messages as Message[];
    }
    return [];
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Late restore: interviewMessagesCache may arrive after mount (context hydrates
  // from sessionStorage in a useEffect).  Apply it once when it becomes available.
  useEffect(() => {
    if (messagesCacheAppliedRef.current || !interviewMessagesCache) return;
    if (
      activeSessionId &&
      interviewMessagesCache.sessionId === activeSessionId &&
      Date.now() - interviewMessagesCache.savedAt < 10 * 60 * 1000
    ) {
      messagesCacheAppliedRef.current = true;
      setMessages(interviewMessagesCache.messages as Message[]);
    }
  }, [interviewMessagesCache, activeSessionId]);

  const [supplements, setSupplements] = useState<EventSupplementItem[]>([]);
  const [pendingEvents, setPendingEvents] = useState<PendingEventDetail[]>([]);
  const [positiveTriggers, setPositiveTriggers] = useState<string[]>([]);
  const [sensitiveTopics, setSensitiveTopics] = useState<string[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // Per-panel loading state: false = loading (bootstrap not yet arrived), true = has data
  const [supplementsLoaded, setSupplementsLoaded] = useState(false);
  const [pendingEventsLoaded, setPendingEventsLoaded] = useState(false);
  const [anchorsLoaded, setAnchorsLoaded] = useState(false);

  const isConnected = session !== null && state !== "closed" && state !== "idle_timeout";
  const isProcessing = state === "processing" || state === "flushing";

  // Merge consecutive same-speaker messages for display
  const mergedMessages = useMemo(() => mergeConsecutiveMessages(messages), [messages]);

  // Persist messages to WorkspaceContext cache (max 100, to avoid sessionStorage quota)
  useEffect(() => {
    const sessionId = session?.session_id ?? activeSessionId;
    if (!sessionId) return;
    // Don't overwrite a valid restored cache with empty messages on mount
    if (messages.length === 0) return;
    setInterviewMessagesCache({
      sessionId,
      messages: messages.slice(-100) as typeof messages,
      savedAt: Date.now(),
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => {
    if (statusEvent) syncFromServerEvent(statusEvent.status, statusEvent.session_id);
  }, [statusEvent, syncFromServerEvent]);

  useEffect(() => {
    if (completedEvent) syncFromServerEvent(completedEvent.status, completedEvent.session_id);
  }, [completedEvent, syncFromServerEvent]);

  useEffect(() => {
    if (!contextEvent) return;

    if (contextEvent.partial === "pending_events") {
      const events = contextEvent.pending_events?.events ?? [];
      setPendingEvents(events);
      setPendingEventsLoaded(true);
      const incomingIds = new Set(events.map((e) => e.id));
      setExpandedIds((prev) => {
        const pruned = new Set<string>();
        prev.forEach((id) => {
          if (incomingIds.has(id)) pruned.add(id);
        });
        return pruned;
      });
      return;
    }

    if (contextEvent.partial === "supplements") {
      setSupplements(contextEvent.event_supplements ?? []);
      setSupplementsLoaded(true);
      return;
    }

    if (contextEvent.partial === "anchors") {
      setPositiveTriggers(contextEvent.positive_triggers ?? []);
      setSensitiveTopics(contextEvent.sensitive_topics ?? []);
      setAnchorsLoaded(true);
      return;
    }

    // Full update (no partial field) — backward-compatible path
    setSupplements(contextEvent.event_supplements ?? []);
    setSupplementsLoaded(true);
    setPositiveTriggers(contextEvent.positive_triggers ?? []);
    setSensitiveTopics(contextEvent.sensitive_topics ?? []);
    setAnchorsLoaded(true);

    const events = contextEvent.pending_events?.events ?? [];
    setPendingEvents(events);
    setPendingEventsLoaded(true);

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

  // Reset per-panel loading flags when a new session is created
  useEffect(() => {
    if (isConnected) {
      setSupplementsLoaded(false);
      setPendingEventsLoaded(false);
      setAnchorsLoaded(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.session_id]);

  const handleCreate = useCallback(async () => {
    if (!username) return;
    await create(username);
  }, [create, username]);

  const handleToggle = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const statusLabel = isProcessing
    ? { status: "loading" as const, text: "处理中" }
    : isConnected
      ? { status: "success" as const, text: "已连接" }
      : error
        ? { status: "error" as const, text: "有错误" }
        : { status: "idle" as const, text: "未开始" };

  const sseLabel =
    isConnected && connectionState === "reconnecting"
      ? { status: "loading" as const, text: "重连中" }
      : isConnected && connectionState === "fatal"
        ? { status: "error" as const, text: "连接失败" }
        : null;

  return (
    <main
      className="flex h-full flex-col overflow-hidden"
    >
      {/* Status bar */}
      <div className="shrink-0 flex items-center justify-end gap-2 px-6 py-3 border-b border-black/[0.06] bg-white/80 backdrop-blur-sm">
        {sseLabel && <StatusBadge status={sseLabel.status} label={sseLabel.text} />}
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
              {state === "session_conflict" ? (
                <>
                  <p className="text-center text-sm text-slate-600">
                    检测到已有进行中的会话，是否继续？
                  </p>
                  <Button
                    onClick={() => recoverFromConflict(recoverableSessionId!, username)}
                    disabled={!recoverableSessionId}
                    className="w-full"
                  >
                    继续已有会话
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void handleCreate()}
                    className="text-slate-500"
                  >
                    重新创建会话
                  </Button>
                </>
              ) : (
                <>
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
                </>
              )}
            </div>
          )}

          {state === "creating_session" && (
            <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
              正在创建会话…
            </div>
          )}

          {isConnected && (
            <>
              {/* Message list — consecutive same-speaker messages are merged */}
              <div className="flex-1 overflow-y-auto space-y-3 px-4 py-4">
                {mergedMessages.length === 0 && (
                  <p className="pt-8 text-center text-xs text-slate-400">
                    点击录音按钮开始采访
                  </p>
                )}
                {mergedMessages.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex ${msg.role === "interviewer" ? "justify-start" : "justify-end"}`}
                  >
                    <div className="flex flex-col gap-0.5 max-w-[80%]">
                      <span
                        className={`text-[10px] ${
                          msg.role === "interviewer" ? "text-slate-400 pl-1" : "text-[#A2845E]/60 pr-1 text-right"
                        }`}
                      >
                        {msg.role === "interviewer" ? "采访者" : (username || "受访者")}
                      </span>
                      <div
                        className={`rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                          msg.role === "interviewer"
                            ? "rounded-tl-sm bg-slate-100 text-slate-800"
                            : "rounded-tr-sm bg-[#A2845E] text-white"
                        }`}
                      >
                        {msg.content}
                      </div>
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

              {/* Voice input area */}
              <div className="shrink-0 border-t border-slate-200 p-3">
                <VoiceRecordPanel
                  username={username || "受访者"}
                  onSegment={(seg) => {
                    const role: SpeakerRole = seg.speaker === "interviewer" ? "interviewer" : "interviewee";
                    setMessages((prev) => [
                      ...prev,
                      { role, content: seg.content, at: new Date().toISOString() },
                    ]);
                    void send(seg.content, seg.speaker);
                  }}
                  disabled={!canSubmitCommand}
                />
              </div>
            </>
          )}
        </div>

        {/* RIGHT: three-panel assist area */}
        <div className="grid flex-1 grid-cols-2 grid-rows-2 gap-4 overflow-hidden p-6">
          <Card className="row-span-2 min-h-0 overflow-hidden p-5">
            {isConnected && !supplementsLoaded ? (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">加载中…</div>
            ) : (
              <BackgroundSupplementPanel supplements={supplements} />
            )}
          </Card>

          <Card className="min-h-0 overflow-hidden p-5">
            {isConnected && !pendingEventsLoaded ? (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">加载中…</div>
            ) : (
              <PendingEventsPanel events={pendingEvents} expandedIds={expandedIds} onToggle={handleToggle} />
            )}
          </Card>

          <Card className="min-h-0 overflow-hidden p-5">
            {isConnected && !anchorsLoaded ? (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">加载中…</div>
            ) : (
              <EmotionalAnchorsPanel positiveTriggers={positiveTriggers} sensitiveTopics={sensitiveTopics} />
            )}
          </Card>
        </div>
      </div>
    </main>
  );
}
