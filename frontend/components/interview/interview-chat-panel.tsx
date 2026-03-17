import type { RefObject } from "react";
import { RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VoiceRecordPanel } from "./voice-record-panel";
import type { MergedInterviewMessage } from "./interview-message-utils";

type InterviewChatPanelProps = {
  sessionUsername?: string;
  username: string | null;
  isConnected: boolean;
  isProcessing: boolean;
  state: string;
  error: { message: string } | null;
  canSubmitCommand: boolean;
  recoverableSessionId: string | null;
  mergedMessages: MergedInterviewMessage[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onCreate: () => void;
  onForceCreate: () => void;
  onRecoverFromConflict: () => void;
  onFlush: () => void;
  onClose: () => void;
  onSegment: (segment: { speaker: string; content: string }) => void;
};

export function InterviewChatPanel({
  sessionUsername,
  username,
  isConnected,
  isProcessing,
  state,
  error,
  canSubmitCommand,
  recoverableSessionId,
  mergedMessages,
  messagesEndRef,
  onCreate,
  onForceCreate,
  onRecoverFromConflict,
  onFlush,
  onClose,
  onSegment,
}: InterviewChatPanelProps) {
  return (
    <div className="flex w-[420px] shrink-0 flex-col border-r border-slate-200/70 bg-white">
      <div className="shrink-0 border-b border-slate-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.14em] text-slate-500">
            {sessionUsername ? `采访对象 · ${sessionUsername}` : "对话区"}
          </p>
          {isConnected && (
            <div className="flex gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={onFlush}
                disabled={!canSubmitCommand}
                title="刷新上下文"
                aria-label="刷新上下文"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
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
              <p className="text-center text-sm text-slate-600">检测到已有进行中的会话，是否继续？</p>
              <Button
                onClick={onRecoverFromConflict}
                disabled={!recoverableSessionId}
                className="w-full"
              >
                继续已有会话
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onForceCreate}
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
              {error && <p className="text-center text-xs text-rose-600">{error.message}</p>}
              <Button
                onClick={onCreate}
                disabled={!username}
                className="w-full"
              >
                创建会话
              </Button>
            </>
          )}
        </div>
      )}

      {state === "creating_session" && !isConnected && (
        <div className="flex flex-1 items-center justify-center text-sm text-slate-500">正在创建会话…</div>
      )}

      {isConnected && (
        <>
          <div className="flex-1 overflow-y-auto mask-fade-both space-y-3 px-4 py-4">
            {mergedMessages.length === 0 && (
              <p className="pt-8 text-center text-xs text-slate-400">点击录音按钮开始采访</p>
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

          <div className="shrink-0 border-t border-slate-200 p-3">
            <VoiceRecordPanel
              username={username || "受访者"}
              onSegment={onSegment}
              disabled={!canSubmitCommand}
            />
          </div>
        </>
      )}
    </div>
  );
}
