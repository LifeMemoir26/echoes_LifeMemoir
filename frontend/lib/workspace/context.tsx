"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken, getToken, getSavedUsername, isTokenExpired } from "@/lib/auth/token";

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

  // Initialise from localStorage after mount to avoid SSR hydration mismatch
  useEffect(() => {
    const stored = getToken();
    if (stored && !isTokenExpired(stored)) {
      setToken(stored);
      const savedUsername = getSavedUsername();
      if (savedUsername) setUsername(savedUsername);
    } else {
      clearToken();
    }
  }, []);

  const isAuthenticated = token !== null && !isTokenExpired(token);

  const logout = () => {
    clearToken();
    setToken(null);
    setUsername("");
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
      logout
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeSessionId, interviewSummary, isAuthenticated, lastTraceId, timelineSummary, token, username]
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
