import { useCallback, useState } from "react";
import type {
  EventSupplementItem,
  InterviewStreamContext,
  PendingEventDetail,
} from "@/lib/api/types";
import { togglePendingEventPriority } from "@/lib/api/interview";

export function useInterviewPanelState(
  contextEvent: InterviewStreamContext | null,
  sessionId?: string | null,
  isConnected?: boolean,
) {
  const [supplements, setSupplements] = useState<EventSupplementItem[]>([]);
  const [pendingEvents, setPendingEvents] = useState<PendingEventDetail[]>([]);
  const [positiveTriggers, setPositiveTriggers] = useState<string[]>([]);
  const [sensitiveTopics, setSensitiveTopics] = useState<string[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // Per-panel loading state: false = loading (bootstrap not yet arrived), true = has data
  const [supplementsLoaded, setSupplementsLoaded] = useState(false);
  const [pendingEventsLoaded, setPendingEventsLoaded] = useState(false);
  const [anchorsLoaded, setAnchorsLoaded] = useState(false);

  const pruneExpandedIds = useCallback((events: PendingEventDetail[]) => {
    const incomingIds = new Set(events.map((e) => e.id));
    setExpandedIds((prev) => {
      const pruned = new Set<string>();
      prev.forEach((id) => {
        if (incomingIds.has(id)) pruned.add(id);
      });
      return pruned;
    });
  }, []);

  // Derive state from contextEvent during render (avoids setState-in-effect)
  const [prevContextEvent, setPrevContextEvent] =
    useState<InterviewStreamContext | null>(null);
  if (contextEvent && contextEvent !== prevContextEvent) {
    setPrevContextEvent(contextEvent);

    if (contextEvent.partial === "pending_events") {
      const events = contextEvent.pending_events?.events ?? [];
      setPendingEvents(events);
      setPendingEventsLoaded(true);
      pruneExpandedIds(events);
    } else if (contextEvent.partial === "supplements") {
      setSupplements(contextEvent.event_supplements ?? []);
      setSupplementsLoaded(true);
    } else if (contextEvent.partial === "anchors") {
      setPositiveTriggers(contextEvent.positive_triggers ?? []);
      setSensitiveTopics(contextEvent.sensitive_topics ?? []);
      setAnchorsLoaded(true);
    } else {
      // Full update (no partial field) — backward-compatible path
      setSupplements(contextEvent.event_supplements ?? []);
      setSupplementsLoaded(true);
      setPositiveTriggers(contextEvent.positive_triggers ?? []);
      setSensitiveTopics(contextEvent.sensitive_topics ?? []);
      setAnchorsLoaded(true);

      const events = contextEvent.pending_events?.events ?? [];
      setPendingEvents(events);
      setPendingEventsLoaded(true);
      pruneExpandedIds(events);
    }
  }

  // Reset per-panel loading flags when a new session is created (render-time)
  const [prevSessionKey, setPrevSessionKey] = useState<string | null>(null);
  const sessionKey = isConnected ? (sessionId ?? "__connected__") : null;
  if (sessionKey !== prevSessionKey) {
    setPrevSessionKey(sessionKey);
    if (isConnected) {
      setSupplementsLoaded(false);
      setPendingEventsLoaded(false);
      setAnchorsLoaded(false);
    }
  }

  const handleToggle = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleTogglePriority = useCallback(
    (eventId: string) => {
      if (!sessionId) return;
      // Optimistic: flip locally for instant feedback
      setPendingEvents((prev) =>
        prev.map((e) =>
          e.id === eventId ? { ...e, is_priority: !e.is_priority } : e,
        ),
      );
      // Fire-and-forget; SSE will push the authoritative list
      togglePendingEventPriority(sessionId, eventId).catch(() => {
        // Revert on failure — SSE will correct eventually anyway
      });
    },
    [sessionId],
  );

  return {
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
  };
}
