"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken, getToken, getSavedUsername, isTokenExpired } from "@/lib/auth/token";
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
  token: string | null;
  setToken: (value: string | null) => void;
  isAuthenticated: boolean;
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
  const [token, setToken] = useState<string | null>(null);
  const [timelineCache, setTimelineCache] = useState<TimelineGenerationCache | null>(null);
  const [interviewMessagesCache, setInterviewMessagesCache] = useState<InterviewMessagesCache | null>(null);

  // ── Bootstrap from localStorage (auth) + sessionStorage (caches) ──────────
  useEffect(() => {
    const stored = getToken();
    if (stored && !isTokenExpired(stored)) {
      setToken(stored);
      const savedUsername = getSavedUsername();
      if (savedUsername) {
        setUsername(savedUsername);

        // Restore timeline cache
        try {
          const raw = sessionStorage.getItem(ssKey("tl_cache", savedUsername));
          if (raw) {
            const parsed: TimelineGenerationCache = JSON.parse(raw);
            if (isFresh(parsed.savedAt)) {
              // Pending requests can't survive a full refresh — silently discard
              if (parsed.phase !== "pending") {
                setTimelineCache(parsed);
              }
            }
          }
        } catch { /* ignore malformed cache */ }

        // Restore interview messages cache
        try {
          const raw = sessionStorage.getItem(ssKey("iv_cache", savedUsername));
          if (raw) {
            const parsed: InterviewMessagesCache = JSON.parse(raw);
            if (isFresh(parsed.savedAt)) {
              setInterviewMessagesCache(parsed);
            }
          }
        } catch { /* ignore malformed cache */ }
      }
    } else {
      clearToken();
    }
  }, []);

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

  const isAuthenticated = token !== null && !isTokenExpired(token);

  const logout = () => {
    clearToken();
    setToken(null);
    setUsername("");
    setTimelineCache(null);
    setInterviewMessagesCache(null);
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
      token,
      setToken,
      isAuthenticated,
      logout,
      timelineCache,
      setTimelineCache,
      interviewMessagesCache,
      setInterviewMessagesCache,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeSessionId, interviewMessagesCache, interviewSummary, isAuthenticated, lastTraceId, timelineCache, timelineSummary, token, username]
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
