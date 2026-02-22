"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  BookOpen,
  BrainCircuit,
  Image as ImageIcon,
  LayoutDashboard,
  Menu,
  MessageSquare,
  Sparkles,
  UploadCloud,
  UserRound,
  X
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { normalizeUnknownError } from "@/lib/api/client";
import { processKnowledgeFile } from "@/lib/api/knowledge";
import type { NormalizedApiError } from "@/lib/api/types";
import { useGenerateMemoir } from "@/lib/hooks/use-generate-memoir";
import { useGenerateTimeline } from "@/lib/hooks/use-generate-timeline";
import { useInterviewEvents } from "@/lib/hooks/use-interview-events";
import { useInterviewSession } from "@/lib/hooks/use-interview-session";
import { useWorkspaceContext } from "@/lib/workspace/context";

const formSchema = z.object({
  username: z.string().min(1, "请输入用户名"),
  target_length: z.coerce.number().min(200, "最少 200 字").max(100000, "最多 100000 字"),
  user_preferences: z.string().optional(),
  timeline_ratio: z.coerce.number().min(0, "最小 0").max(1, "最大 1")
});

type FormValues = z.infer<typeof formSchema>;
type WorkspaceView = "dashboard" | "interview" | "memoir" | "timeline" | "image-studio";

const views: Array<{ key: WorkspaceView; label: string; icon: React.ReactNode }> = [
  { key: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
  { key: "interview", label: "Interview", icon: <MessageSquare className="h-4 w-4" /> },
  { key: "timeline", label: "Timeline", icon: <BookOpen className="h-4 w-4" /> },
  { key: "memoir", label: "Memoir", icon: <UserRound className="h-4 w-4" /> },
  { key: "image-studio", label: "Image Studio", icon: <ImageIcon className="h-4 w-4" /> }
];

function MemoirReaderWorkspace() {
  const inFlightRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [activeView, setActiveView] = useState<WorkspaceView>("memoir");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [shellError, setShellError] = useState<NormalizedApiError | null>(null);
  const [interviewDraft, setInterviewDraft] = useState("");

  const [uploadState, setUploadState] = useState<{
    isUploading: boolean;
    successMessage: string | null;
    error: NormalizedApiError | null;
  }>({ isUploading: false, successMessage: null, error: null });

  const {
    username,
    setUsername,
    activeSessionId,
    setActiveSessionId,
    lastTraceId,
    setLastTraceId,
    interviewSummary,
    setInterviewSummary,
    timelineSummary,
    setTimelineSummary
  } = useWorkspaceContext();

  const { register, handleSubmit, formState, getValues, watch, setValue } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      username: username || "",
      target_length: 2000,
      user_preferences: "温暖、克制、重视家庭细节",
      timeline_ratio: 0.3
    }
  });

  const watchedUsername = watch("username");

  const memoir = useGenerateMemoir();
  const timeline = useGenerateTimeline();
  const interviewSession = useInterviewSession();
  const interviewEvents = useInterviewEvents(interviewSession.session?.session_id ?? null);

  useEffect(() => {
    setUsername((watchedUsername || "").trim());
  }, [setUsername, watchedUsername]);

  // Sync auth username into form whenever context username changes
  useEffect(() => {
    if (username) setValue("username", username);
  }, [username, setValue]);

  useEffect(() => {
    const latest = interviewEvents.completedEvent ?? interviewEvents.statusEvent;
    interviewSession.syncFromServerEvent(latest?.status, latest?.session_id);
  }, [interviewEvents.completedEvent, interviewEvents.statusEvent, interviewSession]);

  useEffect(() => {
    setActiveSessionId(interviewSession.session?.session_id ?? null);
  }, [interviewSession.session?.session_id, setActiveSessionId]);

  useEffect(() => {
    const traceId =
      memoir.data?.trace_id ??
      timeline.data?.trace_id ??
      interviewSession.lastAction?.trace_id ??
      interviewEvents.summary.lastTraceId ??
      null;
    setLastTraceId(traceId);
  }, [
    interviewEvents.summary.lastTraceId,
    interviewSession.lastAction?.trace_id,
    memoir.data?.trace_id,
    setLastTraceId,
    timeline.data?.trace_id
  ]);

  useEffect(() => {
    setInterviewSummary({
      status: interviewSession.state,
      eventCount: interviewEvents.summary.eventCount,
      lastEventId: interviewEvents.lastEventId
    });
  }, [interviewEvents.lastEventId, interviewEvents.summary.eventCount, interviewSession.state, setInterviewSummary]);

  useEffect(() => {
    setTimelineSummary({
      eventCount: timeline.data?.event_count ?? 0,
      generatedAt: timeline.data?.generated_at ?? null
    });
  }, [setTimelineSummary, timeline.data?.event_count, timeline.data?.generated_at]);

  const globalError = shellError ?? interviewSession.error ?? interviewEvents.error ?? timeline.error ?? memoir.normalizedError;

  const statusLabel = useMemo(() => {
    if (memoir.isPending || timeline.isPending || interviewSession.inFlightCommand) {
      return { status: "loading" as const, text: "处理中" };
    }
    if (globalError) {
      return { status: "error" as const, text: "有错误" };
    }
    if (memoir.data || timeline.data || interviewSession.session) {
      return { status: "success" as const, text: "可用" };
    }
    return { status: "idle" as const, text: "待开始" };
  }, [
    globalError,
    interviewSession.inFlightCommand,
    interviewSession.session,
    memoir.data,
    memoir.isPending,
    timeline.data,
    timeline.isPending
  ]);

  const sidebarItem = (view: WorkspaceView, label: string, icon: React.ReactNode) => (
    <button
      key={view}
      type="button"
      onClick={() => {
        setActiveView(view);
        setMobileNavOpen(false);
      }}
      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${
        activeView === view
          ? "bg-[#A2845E]/18 text-white ring-1 ring-[#C4A882]/35"
          : "text-slate-300 hover:bg-slate-800 hover:text-slate-100"
      }`}
    >
      <span className="text-current">{icon}</span>
      <span>{label}</span>
    </button>
  );

  const onMemoirSubmit = handleSubmit(async (values) => {
    await memoir.mutateAsync({
      username: values.username,
      target_length: values.target_length,
      user_preferences: values.user_preferences,
      auto_save: true
    });
  });

  const onFormSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (memoir.isPending || inFlightRef.current) return;
    inFlightRef.current = true;
    setShellError(null);
    try {
      await onMemoirSubmit(event);
    } catch {
      // normalized in hook
    } finally {
      inFlightRef.current = false;
    }
  };

  const handleTimelineGenerate = async () => {
    const values = getValues();
    await timeline.submit({
      username: values.username,
      ratio: values.timeline_ratio,
      user_preferences: values.user_preferences,
      auto_save: false
    });
  };

  const handleEnsureSession = async () => {
    const name = (getValues("username") || "").trim();
    if (!name) {
      setShellError({ code: "INVALID_USERNAME", message: "请先填写用户名", retryable: false });
      return;
    }

    await interviewSession.create(name);
  };

  const handleSendInterviewMessage = async () => {
    const message = interviewDraft.trim();
    if (!message) return;

    const sent = await interviewSession.send(message);
    if (sent) {
      setInterviewDraft("");
    }
  };

  const handleFlushInterview = async () => {
    await interviewSession.flush();
  };

  const handleCloseInterview = async () => {
    await interviewSession.close();
    interviewEvents.disconnect();
  };

  const handleRecoverConflictSession = () => {
    const existingSessionId = interviewSession.recoverableSessionId;
    const name = (getValues("username") || "").trim();
    if (!existingSessionId || !name) {
      return;
    }
    interviewSession.recoverFromConflict(existingSessionId, name);
  };

  const handleKnowledgeUpload = async (file: File | null) => {
    if (!file) return;
    const name = (getValues("username") || "").trim();
    if (!name) {
      setUploadState({
        isUploading: false,
        successMessage: null,
        error: {
          code: "INVALID_USERNAME",
          message: "请先填写用户名再上传素材",
          retryable: false
        }
      });
      return;
    }

    setUploadState({ isUploading: true, successMessage: null, error: null });
    try {
      const result = await processKnowledgeFile(name, file);
      setUploadState({
        isUploading: false,
        successMessage: `上传并处理完成：${result.original_filename}`,
        error: null
      });
    } catch (error) {
      setUploadState({
        isUploading: false,
        successMessage: null,
        error: normalizeUnknownError(error, "上传失败")
      });
    }
  };

  const renderHeader = () => (
    <header className="border-b border-slate-200/70 bg-white/90 px-4 py-4 backdrop-blur md:px-8">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button type="button" variant="secondary" className="lg:hidden" onClick={() => setMobileNavOpen(true)} aria-label="打开导航菜单">
            <Menu className="h-4 w-4" />
          </Button>
          <div>
            <p className="mb-1 text-xs uppercase tracking-[0.2em] text-[#A2845E]">Replica Workspace</p>
            <h1 className="font-[var(--font-heading)] text-3xl text-slate-900">回忆录阅读</h1>
          </div>
        </div>
        <StatusBadge status={statusLabel.status} label={statusLabel.text} />
      </div>
    </header>
  );

  const renderSidebar = () => (
    <>
      <aside className="sticky top-0 hidden h-screen w-72 shrink-0 border-r border-slate-800 bg-slate-900/95 px-5 py-6 backdrop-blur lg:flex lg:flex-col">
        <div className="mb-8 flex items-center gap-3 px-1">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-tr from-[var(--workspace-gold)] to-[var(--workspace-gold-soft)] text-slate-900 shadow-lg shadow-amber-500/30">
            <BrainCircuit className="h-5 w-5" />
          </div>
          <div>
            <p className="font-[var(--font-heading)] text-xl text-white">Echoes</p>
            <p className="text-xs tracking-[0.14em] text-slate-400">LIFE MEMOIR</p>
          </div>
        </div>

        <nav className="space-y-1.5">{views.map((item) => sidebarItem(item.key, item.label, item.icon))}</nav>

        <div className="mt-auto rounded-xl border border-slate-800 bg-slate-950/60 p-4">
          <p className="mb-1 text-xs uppercase tracking-[0.12em] text-slate-400">联通状态</p>
          <p className="text-sm text-slate-200">username：{username || "-"}</p>
          <p className="text-sm text-slate-200">session：{activeSessionId || "-"}</p>
          <p className="text-sm text-slate-200">trace：{lastTraceId || "-"}</p>
        </div>
      </aside>

      {mobileNavOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-950/55 lg:hidden">
          <aside className="h-full w-72 border-r border-slate-800 bg-slate-900/95 px-5 py-6 shadow-xl backdrop-blur">
            <div className="mb-8 flex items-center justify-between">
              <p className="font-[var(--font-heading)] text-xl text-white">Echoes</p>
              <Button type="button" variant="secondary" onClick={() => setMobileNavOpen(false)} aria-label="关闭导航菜单">
                <X className="h-4 w-4" />
              </Button>
            </div>
            <nav className="space-y-1.5">{views.map((item) => sidebarItem(item.key, item.label, item.icon))}</nav>
          </aside>
        </div>
      ) : null}
    </>
  );

  return (
    <main className="min-h-screen bg-[var(--workspace-bg)] text-[var(--workspace-fg)]">
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px]">
        {renderSidebar()}

        <section className="flex min-h-screen flex-1 flex-col">
          {renderHeader()}

          <div className="flex-1 bg-[radial-gradient(circle_at_top,_#FDF6EE_0%,_#fafaf8_45%,_#fafaf8_100%)] p-4 md:p-8">
            {globalError ? (
              <div className="mb-4">
                <ErrorBanner
                  code={globalError.code}
                  message={`${globalError.message}（retryable: ${String(globalError.retryable)}）`}
                  retryable={globalError.retryable}
                  traceId={globalError.traceId}
                  onRetry={globalError.retryable ? () => setShellError(null) : undefined}
                />
              </div>
            ) : null}

            {activeView === "dashboard" ? (
              <div className="grid gap-4 md:grid-cols-3">
                <Card className="md:col-span-2">
                  <h2 className="mb-2 font-[var(--font-heading)] text-2xl text-slate-900">Persona Dashboard</h2>
                  <p className="text-sm text-slate-600">采访、时间线、回忆录共享同一工作台上下文。</p>
                  <div className="mt-4 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
                    <p>用户名：{username || "-"}</p>
                    <p>Session ID：{activeSessionId || "-"}</p>
                    <p>Interview 状态：{interviewSummary.status || "-"}</p>
                    <p>Interview 事件数：{interviewSummary.eventCount}</p>
                    <p>Timeline 事件数：{timelineSummary.eventCount}</p>
                    <p>最后 Trace：{lastTraceId || "-"}</p>
                  </div>
                </Card>
                <Card>
                  <p className="text-xs uppercase tracking-[0.18em] text-[#A2845E]">最近结果</p>
                  <p className="mt-3 text-sm text-slate-700">字数：{memoir.data?.length ?? "-"}</p>
                  <p className="text-sm text-slate-700">Timeline：{timeline.data?.event_count ?? "-"}</p>
                </Card>
              </div>
            ) : null}

            {activeView === "interview" ? (
              <Card>
                <h2 className="mb-2 font-[var(--font-heading)] text-2xl text-slate-900">Interview</h2>
                <p className="mb-4 text-slate-600">支持 create / message / flush / close 与 SSE 断线重连。</p>

                <div className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto_auto]">
                  <Input
                    aria-label="访谈输入"
                    placeholder="输入一段访谈内容"
                    value={interviewDraft}
                    onChange={(event) => setInterviewDraft(event.target.value)}
                  />
                  <Button type="button" variant="secondary" onClick={() => void handleEnsureSession()} disabled={Boolean(interviewSession.inFlightCommand)}>
                    建立会话
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void handleSendInterviewMessage()}
                    disabled={!interviewSession.session?.session_id || !interviewDraft.trim() || !interviewSession.canSubmitCommand}
                  >
                    发送消息
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void handleFlushInterview()}
                    disabled={!interviewSession.session?.session_id || !interviewSession.canSubmitCommand}
                  >
                    Flush
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void handleCloseInterview()}
                    disabled={!interviewSession.session?.session_id || Boolean(interviewSession.inFlightCommand)}
                  >
                    关闭会话
                  </Button>
                </div>

                <div className="mt-4 grid gap-2 text-sm text-slate-700 md:grid-cols-2" aria-live="polite">
                  <p>Session ID：{interviewSession.session?.session_id ?? "-"}</p>
                  <p>Thread ID：{interviewSession.session?.thread_id ?? "-"}</p>
                  <p>命令状态：{interviewSession.state}</p>
                  <p>SSE 连接：{interviewEvents.connectionState}</p>
                  <p>Last-Event-ID：{interviewEvents.lastEventId ?? "-"}</p>
                  <p>最新状态事件：{interviewEvents.statusEvent?.status ?? interviewEvents.completedEvent?.status ?? "-"}</p>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" onClick={() => interviewEvents.reconnectNow()}>
                    手动重连 SSE
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => interviewEvents.disconnect()}>
                    断开 SSE
                  </Button>
                </div>

                {interviewSession.error?.code === "SESSION_CONFLICT" && interviewSession.recoverableSessionId ? (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    <p>检测到同用户名已有活跃会话：{interviewSession.recoverableSessionId}</p>
                    <div className="mt-2">
                      <Button type="button" variant="secondary" onClick={handleRecoverConflictSession}>
                        恢复该会话
                      </Button>
                    </div>
                  </div>
                ) : null}

                <div className="mt-4 max-h-52 overflow-auto rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                  {interviewEvents.events.length === 0 ? (
                    <p>暂无事件</p>
                  ) : (
                    interviewEvents.events.map((evt, idx) => (
                      <p key={`${evt.id}-${idx}`}>
                        [{evt.event}] #{evt.id || "-"}
                      </p>
                    ))
                  )}
                </div>
              </Card>
            ) : null}

            {activeView === "timeline" ? (
              <Card>
                <h2 className="mb-2 font-[var(--font-heading)] text-2xl text-slate-900">Timeline</h2>
                <p className="mb-4 text-slate-600">支持参数输入、单飞行、失败重试与 trace 展示。</p>

                <div className="grid gap-4 md:grid-cols-3">
                  <div>
                    <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">用户名</span>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                      {username || "—"}
                    </div>
                    <input type="hidden" {...register("username")} />
                  </div>
                  <label>
                    <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">时间线比例</span>
                    <Input aria-label="时间线比例" type="number" step="0.1" {...register("timeline_ratio")} />
                  </label>
                  <label className="md:col-span-1">
                    <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">叙事偏好</span>
                    <Input aria-label="叙事偏好" {...register("user_preferences")} />
                  </label>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Button type="button" onClick={() => void handleTimelineGenerate()} disabled={timeline.isPending}>
                    {timeline.isPending ? "生成中" : "生成时间线"}
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => void timeline.retry()} disabled={!timeline.canRetry || timeline.isPending}>
                    重试
                  </Button>
                </div>

                <div className="mt-4 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
                  <p>状态：{timeline.phase}</p>
                  <p>事件数：{timeline.data?.event_count ?? "-"}</p>
                  <p>Trace：{timeline.data?.trace_id ?? timeline.error?.traceId ?? "-"}</p>
                  <p>最后输入：{timeline.lastRequest ? JSON.stringify(timeline.lastRequest) : "-"}</p>
                </div>

                <div className="mt-4 max-h-64 overflow-auto rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                  {timeline.data?.timeline?.length ? (
                    timeline.data.timeline.map((event, idx) => <pre key={idx}>{JSON.stringify(event, null, 2)}</pre>)
                  ) : (
                    <p>暂无时间线事件</p>
                  )}
                </div>
              </Card>
            ) : null}

            {activeView === "memoir" ? (
              <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
                <div className="space-y-6">
                  <Card>
                    <form className="grid gap-4 md:grid-cols-2" onSubmit={onFormSubmit}>
                      <div className="md:col-span-1">
                        <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">用户名</span>
                        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                          {username || "—"}
                        </div>
                        <input type="hidden" {...register("username")} />
                      </div>

                      <label className="md:col-span-1">
                        <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">目标字数</span>
                        <Input aria-label="目标字数" type="number" {...register("target_length")} />
                      </label>

                      <label className="md:col-span-2">
                        <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">叙事偏好</span>
                        <Input aria-label="叙事偏好" {...register("user_preferences")} />
                      </label>

                      <div className="md:col-span-2 flex flex-wrap items-center gap-3">
                        <Button type="submit" disabled={memoir.isPending} aria-label="生成回忆录">
                          <Sparkles className="mr-2 h-4 w-4" />
                          {memoir.isPending ? "生成中" : "生成回忆录"}
                        </Button>
                        <Button
                          type="button"
                          variant="secondary"
                          disabled={uploadState.isUploading}
                          onClick={() => fileInputRef.current?.click()}
                          aria-label="上传知识素材"
                        >
                          <UploadCloud className="mr-2 h-4 w-4" />
                          {uploadState.isUploading ? "上传中" : "上传知识素材"}
                        </Button>
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".txt,.md,.markdown,text/plain"
                          className="hidden"
                          onChange={(event) => {
                            const file = event.target.files?.[0] ?? null;
                            void handleKnowledgeUpload(file);
                            event.currentTarget.value = "";
                          }}
                        />
                      </div>
                    </form>
                  </Card>

                  <Card>
                    <div className="mb-4 flex items-center gap-2">
                      <BookOpen className="h-5 w-5 text-[#A2845E]" />
                      <h2 className="font-[var(--font-heading)] text-2xl text-slate-900">正文预览</h2>
                    </div>

                    {memoir.normalizedError ? (
                      <ErrorBanner
                        code={memoir.normalizedError.code}
                        message={memoir.normalizedError.message}
                        retryable={memoir.normalizedError.retryable}
                        traceId={memoir.normalizedError.traceId}
                        retrying={memoir.isPending}
                        onRetry={
                          memoir.canRetry
                            ? () => {
                                void onMemoirSubmit();
                              }
                            : undefined
                        }
                      />
                    ) : null}

                    {memoir.data ? (
                      <article className="memoir-prose mt-4 text-slate-800">
                        <p>{memoir.data.memoir}</p>
                      </article>
                    ) : (
                      <p className="text-slate-500">尚未生成内容。请先上传素材（可选）并点击“生成回忆录”。</p>
                    )}
                  </Card>
                </div>

                <aside className="space-y-4">
                  <Card>
                    <p className="text-xs uppercase tracking-[0.16em] text-[#A2845E]">运行状态</p>
                    <div className="mt-3 space-y-2 text-sm text-slate-700">
                      <p>字数：{memoir.data?.length ?? "-"}</p>
                      <p>生成时间：{memoir.data?.generated_at ?? "-"}</p>
                      <p>Trace ID：{memoir.data?.trace_id ?? memoir.normalizedError?.traceId ?? lastTraceId ?? "-"}</p>
                    </div>
                  </Card>

                  <Card>
                    <p className="text-xs uppercase tracking-[0.16em] text-[#A2845E]">共享上下文（可选）</p>
                    <p className="mt-2 text-sm text-slate-600">Memoir 在没有 interview/timeline 时也可独立生成。</p>
                    <div className="mt-3 space-y-2 text-sm text-slate-700">
                      <p>Interview 状态：{interviewSummary.status ?? "-"}</p>
                      <p>Timeline 事件数：{timelineSummary.eventCount}</p>
                    </div>
                  </Card>

                  <Card>
                    <p className="text-xs uppercase tracking-[0.16em] text-[#A2845E]">知识上传</p>
                    <p className="mt-2 text-sm text-slate-600">建议先上传 `backend/examples/1.txt`，再生成回忆录以提高内容丰富度。</p>
                    {uploadState.successMessage ? <p className="mt-3 text-sm text-emerald-700">{uploadState.successMessage}</p> : null}
                    {uploadState.error ? (
                      <p className="mt-3 text-sm text-rose-600">
                        {uploadState.error.message}
                        {uploadState.error.traceId ? `（Trace: ${uploadState.error.traceId}）` : ""}
                      </p>
                    ) : null}
                  </Card>
                </aside>
              </div>
            ) : null}

            {activeView === "image-studio" ? (
              <Card>
                <h2 className="mb-2 font-[var(--font-heading)] text-2xl text-slate-900">Image Studio</h2>
                <p className="text-slate-600">保留工作台位置，后续可挂接图片编辑与资源管理任务。</p>
              </Card>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}

export function MemoirReaderPage() {
  return <MemoirReaderWorkspace />;
}
