import React from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoirReaderPage } from "@/components/memoir/memoir-reader-page";
import type { NormalizedApiError } from "@/lib/api/types";

const mutateAsync = vi.fn(async () => undefined);
let mockedError: NormalizedApiError | null = null;
let mockedData:
  | {
      username: string;
      memoir: string;
      length: number;
      trace_id: string;
      generated_at: string;
    }
  | null = null;
let mockedPending = false;

vi.mock("@/lib/hooks/use-generate-memoir", () => ({
  useGenerateMemoir: () => ({
    mutateAsync,
    data: mockedData,
    normalizedError: mockedError,
    isPending: mockedPending,
    canRetry: Boolean(mockedError?.retryable)
  })
}));

vi.mock("@/lib/hooks/use-generate-timeline", () => ({
  useGenerateTimeline: () => ({
    phase: "idle",
    data: null,
    error: null,
    isPending: false,
    canRetry: false,
    lastRequest: null,
    submit: vi.fn(async () => null),
    retry: vi.fn(async () => null),
    reset: vi.fn()
  })
}));

vi.mock("@/lib/hooks/use-interview-session", () => ({
  useInterviewSession: () => ({
    session: null,
    state: "idle",
    summary: {
      sessionId: null,
      threadId: null,
      username: null,
      state: "idle",
      traceId: null
    },
    error: null,
    lastAction: null,
    inFlightCommand: null,
    canSubmitCommand: true,
    create: vi.fn(async () => null),
    send: vi.fn(async () => null),
    flush: vi.fn(async () => null),
    close: vi.fn(async () => null),
    syncFromServerEvent: vi.fn()
  })
}));

vi.mock("@/lib/hooks/use-interview-events", () => ({
  useInterviewEvents: () => ({
    connectionState: "idle",
    events: [],
    statusEvent: null,
    contextEvent: null,
    completedEvent: null,
    error: null,
    lastEventId: null,
    summary: {
      eventCount: 0,
      lastStatus: null,
      lastTraceId: null
    },
    reconnectNow: vi.fn(),
    disconnect: vi.fn()
  })
}));

describe("MemoirReaderPage", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    mutateAsync.mockImplementation(async () => undefined);
    mockedError = null;
    mockedData = null;
    mockedPending = false;
  });

  it("renders base state", () => {
    render(<MemoirReaderPage />);
    expect(screen.getByRole("heading", { name: "回忆录阅读" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成回忆录/ })).toBeInTheDocument();
  });

  it("submits only through explicit action", async () => {
    const user = userEvent.setup();
    render(<MemoirReaderPage />);

    await user.type(screen.getByLabelText("用户名"), "alice");
    await user.click(screen.getByRole("button", { name: /生成回忆录/ }));

    expect(mutateAsync).toHaveBeenCalledTimes(1);
  });

  it("prevents duplicate submit on double click", async () => {
    const user = userEvent.setup();
    let resolveRequest: ((value: undefined) => void) | undefined;
    mutateAsync.mockImplementationOnce(
      () =>
        new Promise<undefined>((resolve) => {
          resolveRequest = resolve;
        })
    );

    render(<MemoirReaderPage />);
    await user.type(screen.getByLabelText("用户名"), "alice");
    await user.dblClick(screen.getByRole("button", { name: /生成回忆录/ }));

    expect(mutateAsync).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveRequest?.(undefined);
    });
  });

  it("switches view from mobile drawer navigation", async () => {
    const user = userEvent.setup();
    render(<MemoirReaderPage />);

    await user.click(screen.getByRole("button", { name: "打开导航菜单" }));
    const dashboardButtons = screen.getAllByRole("button", { name: "Dashboard" });
    await user.click(dashboardButtons[dashboardButtons.length - 1]);

    expect(screen.getByRole("heading", { name: "Persona Dashboard" })).toBeInTheDocument();
  });

  it("renders error and trace consistently", () => {
    mockedError = {
      code: "NETWORK_ERROR",
      message: "网络异常",
      retryable: true,
      traceId: "memoir-trace-001"
    };

    render(<MemoirReaderPage />);

    expect(screen.getAllByText(/错误码: NETWORK_ERROR/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Trace: memoir-trace-001/).length).toBeGreaterThan(0);
  });

  it("keeps shared username context consistent across modules", async () => {
    const user = userEvent.setup();
    render(<MemoirReaderPage />);

    await user.type(screen.getByLabelText("用户名"), "alice");
    await user.click(screen.getByRole("button", { name: "打开导航菜单" }));
    const dashboardButtons = screen.getAllByRole("button", { name: "Dashboard" });
    await user.click(dashboardButtons[dashboardButtons.length - 1]);

    expect(screen.getByText("用户名：alice")).toBeInTheDocument();
    expect(screen.getByText("Session ID：-")).toBeInTheDocument();
  });
});
