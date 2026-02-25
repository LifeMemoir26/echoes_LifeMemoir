import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useInterviewPanelState } from "@/components/interview/use-interview-panel-state";
import type { InterviewStreamContext } from "@/lib/api/types";

vi.mock("@/lib/api/interview", () => ({
  togglePendingEventPriority: vi.fn().mockResolvedValue({}),
}));

describe("useInterviewPanelState", () => {
  it("hydrates three panels from full context snapshot", async () => {
    const context: InterviewStreamContext = {
      session_id: "s-1",
      trace_id: "t-1",
      event_supplements: [
        { event_summary: "补充1", event_details: "细节1" },
      ],
      positive_triggers: ["触发点A"],
      sensitive_topics: ["敏感点B"],
      pending_events: {
        total: 1,
        priority_count: 1,
        unexplored_count: 0,
        events: [
          {
            id: "e-1",
            summary: "待深入事件",
            is_priority: true,
            explored_length: 20,
            explored_content: "已探索",
          },
        ],
      },
    };

    const { result, rerender } = renderHook(
      ({ evt }) => useInterviewPanelState(evt, "s-1", true),
      { initialProps: { evt: null as InterviewStreamContext | null } },
    );

    expect(result.current.supplementsLoaded).toBe(false);
    expect(result.current.pendingEventsLoaded).toBe(false);
    expect(result.current.anchorsLoaded).toBe(false);

    rerender({ evt: context });

    await waitFor(() => {
      expect(result.current.supplementsLoaded).toBe(true);
      expect(result.current.pendingEventsLoaded).toBe(true);
      expect(result.current.anchorsLoaded).toBe(true);
    });

    expect(result.current.supplements).toHaveLength(1);
    expect(result.current.pendingEvents).toHaveLength(1);
    expect(result.current.positiveTriggers).toEqual(["触发点A"]);
    expect(result.current.sensitiveTopics).toEqual(["敏感点B"]);
  });

  it("accepts partial SSE context updates", async () => {
    const { result, rerender } = renderHook(
      ({ evt }) => useInterviewPanelState(evt, "s-2", true),
      { initialProps: { evt: null as InterviewStreamContext | null } },
    );

    const pendingPartial: InterviewStreamContext = {
      session_id: "s-2",
      trace_id: "t-2",
      partial: "pending_events",
      pending_events: {
        total: 1,
        priority_count: 0,
        unexplored_count: 1,
        events: [
          {
            id: "e-2",
            summary: "事件2",
            is_priority: false,
            explored_length: 0,
            explored_content: "",
          },
        ],
      },
    };

    rerender({ evt: pendingPartial });

    await waitFor(() => {
      expect(result.current.pendingEventsLoaded).toBe(true);
    });
    expect(result.current.pendingEvents).toHaveLength(1);
    expect(result.current.supplementsLoaded).toBe(false);
    expect(result.current.anchorsLoaded).toBe(false);

    const anchorPartial: InterviewStreamContext = {
      session_id: "s-2",
      trace_id: "t-2",
      partial: "anchors",
      positive_triggers: ["正向"],
      sensitive_topics: ["敏感"],
    };

    rerender({ evt: anchorPartial });

    await waitFor(() => {
      expect(result.current.anchorsLoaded).toBe(true);
    });
    expect(result.current.positiveTriggers).toEqual(["正向"]);
    expect(result.current.sensitiveTopics).toEqual(["敏感"]);
  });

  it("resets loading flags when switching to a new connected session", async () => {
    const fullContext: InterviewStreamContext = {
      session_id: "s-3",
      trace_id: "t-3",
      event_supplements: [],
      positive_triggers: [],
      sensitive_topics: [],
      pending_events: { total: 0, priority_count: 0, unexplored_count: 0, events: [] },
    };

    const { result, rerender } = renderHook(
      ({ evt, sid }) => useInterviewPanelState(evt, sid, true),
      { initialProps: { evt: fullContext as InterviewStreamContext | null, sid: "s-3" } },
    );

    await waitFor(() => {
      expect(result.current.supplementsLoaded).toBe(true);
      expect(result.current.pendingEventsLoaded).toBe(true);
      expect(result.current.anchorsLoaded).toBe(true);
    });

    act(() => {
      rerender({ evt: null, sid: "s-4" });
    });

    await waitFor(() => {
      expect(result.current.supplementsLoaded).toBe(false);
      expect(result.current.pendingEventsLoaded).toBe(false);
      expect(result.current.anchorsLoaded).toBe(false);
    });
  });
});
