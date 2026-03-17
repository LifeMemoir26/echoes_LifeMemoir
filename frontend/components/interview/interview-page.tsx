"use client";

import { useCallback, useEffect } from "react";
import { useInterviewEvents } from "@/lib/hooks/use-interview-events";
import { useInterviewSession } from "@/lib/hooks/use-interview-session";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { StatusBadge } from "@/components/ui/status-badge";
import { InterviewSidePanels } from "./interview-side-panels";
import { useInterviewPanelState } from "./use-interview-panel-state";
import { InterviewChatPanel } from "./interview-chat-panel";
import { useInterviewMessages } from "./use-interview-messages";

export function InterviewPage() {
  const { username, activeSessionId, setActiveSessionId, interviewMessagesCache, setInterviewMessagesCache } = useWorkspaceContext();
  const { session, state, error, canSubmitCommand, create, forceCreate, send, flush, close, syncFromServerEvent, recoverableSessionId, recoverFromConflict } =
    useInterviewSession({
      initialSessionId: activeSessionId,
      initialUsername: username,
    });
  const { contextEvent, statusEvent, completedEvent, connectionState } = useInterviewEvents(session?.session_id ?? null);

  const { mergedMessages, messagesEndRef, appendSegment } = useInterviewMessages({
    activeSessionId,
    currentSessionId: session?.session_id ?? null,
    interviewMessagesCache,
    setInterviewMessagesCache,
    state,
  });

  const isConnected = session !== null && state !== "closed" && state !== "idle_timeout";
  const isProcessing = state === "processing" || state === "flushing";

  const {
    supplements,
    pendingEvents,
    positiveTriggers,
    sensitiveTopics,
    expandedIds,
    supplementsLoaded,
    pendingEventsLoaded,
    anchorsLoaded,
    handleToggle,
    handleTogglePriority,
  } = useInterviewPanelState(contextEvent, session?.session_id, isConnected);

  useEffect(() => {
    if (statusEvent) syncFromServerEvent(statusEvent.status, statusEvent.session_id);
  }, [statusEvent, syncFromServerEvent]);

  useEffect(() => {
    if (completedEvent) syncFromServerEvent(completedEvent.status, completedEvent.session_id);
  }, [completedEvent, syncFromServerEvent]);

  useEffect(() => {
    if (state === "closed" || state === "idle_timeout" || state === "session_not_found") {
      setActiveSessionId(null);
      return;
    }
    if (session?.session_id) {
      setActiveSessionId(session.session_id);
    }
  }, [session?.session_id, setActiveSessionId, state]);

  const handleCreate = useCallback(async () => {
    if (!username) return;
    await create(username);
  }, [create, username]);

  const handleForceCreate = useCallback(async () => {
    if (!username) return;
    await forceCreate(username);
  }, [forceCreate, username]);

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
    <main className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 flex items-center justify-end gap-2 px-6 py-3 border-b border-[#A2845E]/[0.06] bg-[var(--glass-default)] backdrop-blur-[15px] backdrop-saturate-[1.8]">
        {sseLabel && <StatusBadge status={sseLabel.status} label={sseLabel.text} />}
        <StatusBadge status={statusLabel.status} label={statusLabel.text} />
      </div>

      <div className="flex flex-1 overflow-hidden">
        <InterviewChatPanel
          sessionUsername={session?.username}
          username={username}
          isConnected={isConnected}
          isProcessing={isProcessing}
          state={state}
          error={error}
          canSubmitCommand={canSubmitCommand}
          recoverableSessionId={recoverableSessionId}
          mergedMessages={mergedMessages}
          messagesEndRef={messagesEndRef}
          onCreate={() => void handleCreate()}
          onForceCreate={() => void handleForceCreate()}
          onRecoverFromConflict={() => void recoverFromConflict(recoverableSessionId!, username)}
          onFlush={() => void flush()}
          onClose={() => void close()}
          onSegment={(seg) => {
            appendSegment({
              speaker: seg.speaker === "interviewer" ? "interviewer" : "interviewee",
              content: seg.content,
            });
            void send(seg.content, seg.speaker);
          }}
        />

        <InterviewSidePanels
          isConnected={isConnected}
          supplementsLoaded={supplementsLoaded}
          pendingEventsLoaded={pendingEventsLoaded}
          anchorsLoaded={anchorsLoaded}
          supplements={supplements}
          pendingEvents={pendingEvents}
          expandedIds={expandedIds}
          positiveTriggers={positiveTriggers}
          sensitiveTopics={sensitiveTopics}
          onToggle={handleToggle}
          onTogglePriority={handleTogglePriority}
        />
      </div>
    </main>
  );
}
