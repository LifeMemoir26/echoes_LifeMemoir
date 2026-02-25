import { useCallback, useEffect, useMemo, useReducer } from "react";
import type {
  EventSupplementItem,
  InterviewStreamContext,
  PendingEventDetail,
} from "@/lib/api/types";
import { togglePendingEventPriority } from "@/lib/api/interview";

type PanelState = {
  supplements: EventSupplementItem[];
  pendingEvents: PendingEventDetail[];
  positiveTriggers: string[];
  sensitiveTopics: string[];
  expandedIds: Set<string>;
  supplementsLoaded: boolean;
  pendingEventsLoaded: boolean;
  anchorsLoaded: boolean;
  prevSessionKey: string | null;
};

type PanelAction =
  | { type: "apply_context"; contextEvent: InterviewStreamContext | null }
  | { type: "session_changed"; isConnected?: boolean; sessionKey: string | null }
  | { type: "toggle_expanded"; id: string }
  | { type: "toggle_priority_optimistic"; eventId: string };

const initialState: PanelState = {
  supplements: [],
  pendingEvents: [],
  positiveTriggers: [],
  sensitiveTopics: [],
  expandedIds: new Set(),
  supplementsLoaded: false,
  pendingEventsLoaded: false,
  anchorsLoaded: false,
  prevSessionKey: null,
};

function pruneExpandedIds(
  expandedIds: Set<string>,
  events: PendingEventDetail[],
): Set<string> {
  const incomingIds = new Set(events.map((e) => e.id));
  const next = new Set<string>();
  expandedIds.forEach((id) => {
    if (incomingIds.has(id)) next.add(id);
  });
  return next;
}

function reducer(state: PanelState, action: PanelAction): PanelState {
  switch (action.type) {
    case "apply_context": {
      const { contextEvent } = action;
      if (!contextEvent) return state;

      if (contextEvent.partial === "pending_events") {
        const events = contextEvent.pending_events?.events ?? [];
        return {
          ...state,
          pendingEvents: events,
          pendingEventsLoaded: true,
          expandedIds: pruneExpandedIds(state.expandedIds, events),
        };
      }

      if (contextEvent.partial === "supplements") {
        return {
          ...state,
          supplements: contextEvent.event_supplements ?? [],
          supplementsLoaded: true,
        };
      }

      if (contextEvent.partial === "anchors") {
        return {
          ...state,
          positiveTriggers: contextEvent.positive_triggers ?? [],
          sensitiveTopics: contextEvent.sensitive_topics ?? [],
          anchorsLoaded: true,
        };
      }

      // Full update (no partial field) — backward-compatible path
      const events = contextEvent.pending_events?.events ?? [];
      return {
        ...state,
        supplements: contextEvent.event_supplements ?? [],
        supplementsLoaded: true,
        positiveTriggers: contextEvent.positive_triggers ?? [],
        sensitiveTopics: contextEvent.sensitive_topics ?? [],
        anchorsLoaded: true,
        pendingEvents: events,
        pendingEventsLoaded: true,
        expandedIds: pruneExpandedIds(state.expandedIds, events),
      };
    }
    case "session_changed": {
      const { isConnected, sessionKey } = action;
      if (!isConnected) {
        return state;
      }

      const prevKey = state.prevSessionKey;
      const switchedSession = prevKey !== null && prevKey !== sessionKey;
      return {
        ...state,
        prevSessionKey: sessionKey,
        ...(switchedSession
          ? {
              supplementsLoaded: false,
              pendingEventsLoaded: false,
              anchorsLoaded: false,
            }
          : {}),
      };
    }
    case "toggle_expanded": {
      const next = new Set(state.expandedIds);
      if (next.has(action.id)) next.delete(action.id);
      else next.add(action.id);
      return { ...state, expandedIds: next };
    }
    case "toggle_priority_optimistic":
      return {
        ...state,
        pendingEvents: state.pendingEvents.map((e) =>
          e.id === action.eventId ? { ...e, is_priority: !e.is_priority } : e,
        ),
      };
    default:
      return state;
  }
}

export function useInterviewPanelState(
  contextEvent: InterviewStreamContext | null,
  sessionId?: string | null,
  isConnected?: boolean,
) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    dispatch({ type: "apply_context", contextEvent });
  }, [contextEvent]);

  const sessionKey = useMemo(
    () => (isConnected ? (sessionId ?? "__connected__") : null),
    [isConnected, sessionId],
  );

  useEffect(() => {
    dispatch({ type: "session_changed", isConnected, sessionKey });
  }, [isConnected, sessionKey]);

  const handleToggle = useCallback((id: string) => {
    dispatch({ type: "toggle_expanded", id });
  }, []);

  const handleTogglePriority = useCallback(
    (eventId: string) => {
      if (!sessionId) return;
      // Optimistic: flip locally for instant feedback
      dispatch({ type: "toggle_priority_optimistic", eventId });
      // Fire-and-forget; SSE will push the authoritative list
      togglePendingEventPriority(sessionId, eventId).catch(() => {
        // Revert on failure — SSE will correct eventually anyway
      });
    },
    [sessionId],
  );

  return {
    supplements: state.supplements,
    pendingEvents: state.pendingEvents,
    positiveTriggers: state.positiveTriggers,
    sensitiveTopics: state.sensitiveTopics,
    expandedIds: state.expandedIds,
    supplementsLoaded: state.supplementsLoaded,
    pendingEventsLoaded: state.pendingEventsLoaded,
    anchorsLoaded: state.anchorsLoaded,
    handleToggle,
    handleTogglePriority,
  };
}
