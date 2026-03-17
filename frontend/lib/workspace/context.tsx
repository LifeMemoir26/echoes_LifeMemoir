"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { getAuthSession, logoutSession } from "@/lib/api/auth";
import { clearSavedSession, getSavedUsername, saveSessionUsername } from "@/lib/auth/token";
import type { NormalizedApiError, TimelineGenerateData, TimelineGenerateRequest } from "@/lib/api/types";

// ── Timeline generation cache ────────────────────────────────────────────────
export type TimelineGenerationPhase = "idle" | "pending" | "success" | "error";

export type TimelineGenerationCache = {
  phase: TimelineGenerationPhase;
  data: TimelineGenerateData | null;
  error: NormalizedApiError | null;
  lastRequest: TimelineGenerateRequest | null;
  savedAt: number; // Date.now()
};

// ── Interview messages cache ──────────────────────────────────────────────────
export type SpeakerRole = "interviewer" | "interviewee";
export type CachedMessage = { role: SpeakerRole; content: string; at: string };

export type InterviewMessagesCache = {
  sessionId: string;
  messages: CachedMessage[];
  savedAt: number;
};

export type InterviewSessionPointerCache = {
  sessionId: string;
  savedAt: number;
};

// ── TTL ───────────────────────────────────────────────────────────────────────
const CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes

function isFresh(savedAt: number): boolean {
  return Date.now() - savedAt < CACHE_TTL_MS;
}

function ssKey(prefix: string, username: string): string {
  return `${prefix}_${username}`;
}

// ─────────────────────────────────────────────────────────────────────────────

type InterviewSummary = {
  status: string | null;
  eventCount: number;
  lastEventId: string | null;
};

type TimelineSummary = {
  eventCount: number;
  generatedAt: string | null;
};

type WorkspaceContextValue = {
  username: string;
  setUsername: (value: string) => void;
  activeSessionId: string | null;
  setActiveSessionId: (value: string | null) => void;
  lastTraceId: string | null;
  setLastTraceId: (value: string | null) => void;
  interviewSummary: InterviewSummary;
  setInterviewSummary: (value: InterviewSummary) => void;
  timelineSummary: TimelineSummary;
  setTimelineSummary: (value: TimelineSummary) => void;
  authReady: boolean;
  isAuthenticated: boolean;
  markAuthenticated: (username: string) => void;
  logout: () => void;
  // ── Cross-navigation state caches ──────────────────────────────────────────
  timelineCache: TimelineGenerationCache | null;
  setTimelineCache: (v: TimelineGenerationCache | null) => void;
  interviewMessagesCache: InterviewMessagesCache | null;
  setInterviewMessagesCache: (v: InterviewMessagesCache | null) => void;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [lastTraceId, setLastTraceId] = useState<string | null>(null);
  const [interviewSummary, setInterviewSummary] = useState<InterviewSummary>({
    status: null,
    eventCount: 0,
    lastEventId: null
  });
  const [timelineSummary, setTimelineSummary] = useState<TimelineSummary>({
    eventCount: 0,
    generatedAt: null
  });
  const [authReady, setAuthReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [timelineCache, setTimelineCache] = useState<TimelineGenerationCache | null>(null);
  const [interviewMessagesCache, setInterviewMessagesCache] = useState<InterviewMessagesCache | null>(null);

  const restoreCaches = useCallback((nextUsername: string) => {
    setActiveSessionId(null);
    setTimelineCache(null);
    setInterviewMessagesCache(null);

    try {
      const raw = sessionStorage.getItem(ssKey("tl_cache", nextUsername));
      if (raw) {
        const parsed: TimelineGenerationCache = JSON.parse(raw);
        if (isFresh(parsed.savedAt) && parsed.phase !== "pending") {
          setTimelineCache(parsed);
        }
      }
    } catch {
      // ignore malformed cache
    }

    try {
      const raw = sessionStorage.getItem(ssKey("iv_cache", nextUsername));
      if (raw) {
        const parsed: InterviewMessagesCache = JSON.parse(raw);
        if (isFresh(parsed.savedAt)) {
          setInterviewMessagesCache(parsed);
        }
      }
    } catch {
      // ignore malformed cache
    }

    try {
      const raw = sessionStorage.getItem(ssKey("iv_session", nextUsername));
      if (raw) {
        const parsed: InterviewSessionPointerCache = JSON.parse(raw);
        if (isFresh(parsed.savedAt) && parsed.sessionId) {
          setActiveSessionId(parsed.sessionId);
        }
      }
    } catch {
      // ignore malformed cache
    }
  }, []);

  const clearPersistedCaches = useCallback((targetUsername: string | null) => {
    if (!targetUsername) return;
    sessionStorage.removeItem(ssKey("tl_cache", targetUsername));
    sessionStorage.removeItem(ssKey("iv_cache", targetUsername));
    sessionStorage.removeItem(ssKey("iv_session", targetUsername));
  }, []);

  const markAuthenticated = useCallback((nextUsername: string) => {
    saveSessionUsername(nextUsername);
    setUsername(nextUsername);
    restoreCaches(nextUsername);
    setIsAuthenticated(true);
    setAuthReady(true);
  }, [restoreCaches]);

  // ── Bootstrap from server-side session + local cache hints ─────────────────
  useEffect(() => {
    let cancelled = false;

    async function bootstrapAuth() {
      try {
        const session = await getAuthSession();
        if (cancelled) return;
        markAuthenticated(session.username);
      } catch {
        if (cancelled) return;
        const savedUsername = getSavedUsername();
        clearSavedSession();
        clearPersistedCaches(savedUsername);
        setUsername("");
        setTimelineCache(null);
        setInterviewMessagesCache(null);
        setIsAuthenticated(false);
        setAuthReady(true);
      }
    }
    void bootstrapAuth();

    return () => {
      cancelled = true;
    };
  }, [clearPersistedCaches, markAuthenticated]);

  // ── Persist timeline cache to sessionStorage on change ───────────────────
  useEffect(() => {
    if (!username) return;
    const key = ssKey("tl_cache", username);
    if (timelineCache) {
      try { sessionStorage.setItem(key, JSON.stringify(timelineCache)); } catch { /* quota */ }
    } else {
      sessionStorage.removeItem(key);
    }
  }, [timelineCache, username]);

  // ── Persist interview messages cache to sessionStorage on change ──────────
  useEffect(() => {
    if (!username) return;
    const key = ssKey("iv_cache", username);
    if (interviewMessagesCache) {
      try { sessionStorage.setItem(key, JSON.stringify(interviewMessagesCache)); } catch { /* quota */ }
    } else {
      sessionStorage.removeItem(key);
    }
  }, [interviewMessagesCache, username]);

  // ── Persist active interview session pointer for refresh recovery ────────
  useEffect(() => {
    if (!username) return;
    const key = ssKey("iv_session", username);
    if (activeSessionId) {
      const payload: InterviewSessionPointerCache = {
        sessionId: activeSessionId,
        savedAt: Date.now(),
      };
      try {
        sessionStorage.setItem(key, JSON.stringify(payload));
      } catch {
        // ignore quota
      }
    } else {
      sessionStorage.removeItem(key);
    }
  }, [activeSessionId, username]);

  const logout = () => {
    const currentOrSavedUsername = username || getSavedUsername();
    void logoutSession().catch(() => undefined);
    clearSavedSession();
    clearPersistedCaches(currentOrSavedUsername);
    setUsername("");
    setActiveSessionId(null);
    setLastTraceId(null);
    setInterviewSummary({
      status: null,
      eventCount: 0,
      lastEventId: null
    });
    setTimelineSummary({
      eventCount: 0,
      generatedAt: null
    });
    setTimelineCache(null);
    setInterviewMessagesCache(null);
    setIsAuthenticated(false);
    setAuthReady(true);
    router.replace("/login");
  };

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      username,
      setUsername,
      activeSessionId,
      setActiveSessionId,
      lastTraceId,
      setLastTraceId,
      interviewSummary,
      setInterviewSummary,
      timelineSummary,
      setTimelineSummary,
      authReady,
      isAuthenticated,
      markAuthenticated,
      logout,
      timelineCache,
      setTimelineCache,
      interviewMessagesCache,
      setInterviewMessagesCache,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeSessionId, authReady, interviewMessagesCache, interviewSummary, isAuthenticated, lastTraceId, markAuthenticated, timelineCache, timelineSummary, username]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaceContext() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspaceContext must be used inside WorkspaceProvider");
  }
  return ctx;
}
