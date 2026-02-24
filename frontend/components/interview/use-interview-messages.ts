import { useEffect, useMemo, useRef, useState } from "react";
import { mergeConsecutiveMessages } from "./interview-message-utils";
import type { InterviewMessage, SpeakerRole } from "./interview-message-types";

type MessagesCache = {
  sessionId: string;
  messages: InterviewMessage[];
  savedAt: number;
};

type UseInterviewMessagesParams = {
  activeSessionId: string | null;
  currentSessionId: string | null;
  interviewMessagesCache: MessagesCache | null;
  setInterviewMessagesCache: (cache: MessagesCache) => void;
  state: string;
};

export function useInterviewMessages({
  activeSessionId,
  currentSessionId,
  interviewMessagesCache,
  setInterviewMessagesCache,
  state,
}: UseInterviewMessagesParams) {
  const messagesCacheAppliedRef = useRef(false);
  const [messages, setMessages] = useState<InterviewMessage[]>(() => {
    if (
      interviewMessagesCache &&
      activeSessionId &&
      interviewMessagesCache.sessionId === activeSessionId &&
      Date.now() - interviewMessagesCache.savedAt < 10 * 60 * 1000
    ) {
      messagesCacheAppliedRef.current = true;
      return interviewMessagesCache.messages;
    }
    return [];
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesCacheAppliedRef.current || !interviewMessagesCache) return;
    if (
      activeSessionId &&
      interviewMessagesCache.sessionId === activeSessionId &&
      Date.now() - interviewMessagesCache.savedAt < 10 * 60 * 1000
    ) {
      messagesCacheAppliedRef.current = true;
      setMessages(interviewMessagesCache.messages);
    }
  }, [interviewMessagesCache, activeSessionId]);

  const mergedMessages = useMemo(() => mergeConsecutiveMessages(messages), [messages]);

  useEffect(() => {
    const sessionId = currentSessionId ?? activeSessionId;
    if (!sessionId) return;
    if (messages.length === 0) return;

    setInterviewMessagesCache({
      sessionId,
      messages: messages.slice(-100),
      savedAt: Date.now(),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, state]);

  const appendSegment = (segment: { speaker: SpeakerRole; content: string }) => {
    const role: SpeakerRole = segment.speaker === "interviewer" ? "interviewer" : "interviewee";
    setMessages((prev) => [...prev, { role, content: segment.content, at: new Date().toISOString() }]);
  };

  return {
    messages,
    mergedMessages,
    messagesEndRef,
    appendSegment,
  };
}
