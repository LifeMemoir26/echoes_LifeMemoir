"use client";

import { useCallback, useRef, useState } from "react";
import { getAsrSignedUrl } from "@/lib/api/asr";

export type AsrStatus = "idle" | "connecting" | "connected" | "error" | "closed";

/**
 * A finalized or in-progress transcription segment from iFlytek RTASR.
 */
export type AsrSegment = {
  text: string;
  /** Effective speaker number after fallback (always >= 1). */
  roleNumber: number;
  /** Raw rl from iFlytek — 0 means "same as previous", >0 means speaker switch. */
  rawRl: number;
  isFinal: boolean;
};

export type IflytekWord = {
  w: string;
  wp: string;
  rl?: string;
};

/**
 * Parsed iFlytek RTASR response data (the JSON inside `data` field).
 */
type IflytekResultData = {
  cn: {
    st: {
      type: string; // "0" final, "1" intermediate
      rt: Array<{
        ws: Array<{
          cw: Array<IflytekWord>;
        }>;
      }>;
    };
  };
  seg_id: string;
};

function parseRole(rawRl: string | undefined): number {
  if (!rawRl) return 0;
  const parsed = Number.parseInt(rawRl, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function splitFinalWordsByRole(
  words: IflytekWord[],
  previousRole: number
): { segments: AsrSegment[]; lastRole: number } {
  const segments: AsrSegment[] = [];
  let currentRole = previousRole > 0 ? previousRole : 1;
  let currentRawRl = 0;
  let buffer = "";

  const flush = () => {
    const text = buffer.trim();
    if (!text) {
      buffer = "";
      currentRawRl = 0;
      return;
    }
    segments.push({
      text,
      roleNumber: currentRole,
      rawRl: currentRawRl,
      isFinal: true,
    });
    buffer = "";
    currentRawRl = 0;
  };

  for (const word of words) {
    const rl = parseRole(word.rl);
    if (rl > 0 && rl !== currentRole) {
      flush();
      currentRole = rl;
      currentRawRl = rl;
    } else if (rl > 0 && buffer.length === 0) {
      currentRole = rl;
      currentRawRl = rl;
    }

    buffer += word.w;
  }

  flush();
  return { segments, lastRole: currentRole };
}

/**
 * Hook for managing iFlytek RTASR WebSocket connection.
 *
 * Handles: signing URL retrieval, WebSocket lifecycle, JSON parsing,
 * and segment extraction with speaker diarization (`rl` field).
 */
export function useIflytekAsr() {
  const [status, setStatus] = useState<AsrStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [segments, setSegments] = useState<AsrSegment[]>([]);
  const [partialText, setPartialText] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  // Track the latest explicit non-zero role number across finalized results
  const lastRoleRef = useRef<number>(0);
  // Set to false by disconnect() to cancel a concurrent connect() that is awaiting getAsrSignedUrl
  const connectActiveRef = useRef<boolean>(false);

  const connect = useCallback(async () => {
    try {
      // 先关闭任何残留的旧连接，释放并发槽
      const oldWs = wsRef.current;
      if (oldWs) {
        oldWs.onmessage = null;
        oldWs.onerror = null;
        oldWs.onclose = null;
        if (oldWs.readyState === WebSocket.OPEN || oldWs.readyState === WebSocket.CONNECTING) {
          oldWs.close();
        }
        wsRef.current = null;
      }

      setError(null);
      setStatus("connecting");
      setSegments([]);
      setPartialText("");
      lastRoleRef.current = 0;
      connectActiveRef.current = true;

      const { url } = await getAsrSignedUrl();

      // If disconnect() was called while we were awaiting the URL, abort
      if (!connectActiveRef.current) {
        return;
      }

      const ws = new WebSocket(url);
      wsRef.current = ws;

      // Wait for WebSocket to actually open before returning — this ensures
      // audio capture doesn't start sending chunks before the WS is ready.
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => {
          setStatus("connected");
          resolve();
        };

        // If disconnected while waiting for open, treat as abort
        const checkDisconnected = setInterval(() => {
          if (!connectActiveRef.current) {
            clearInterval(checkDisconnected);
            reject(new Error("ABORTED"));
          }
        }, 50);

        ws.onerror = () => {
          clearInterval(checkDisconnected);
          setError("WebSocket 连接错误");
          setStatus("error");
          ws.close();
          if (wsRef.current === ws) wsRef.current = null;
          reject(new Error("WebSocket 连接错误"));
        };

        ws.onclose = () => {
          clearInterval(checkDisconnected);
          if (wsRef.current === ws) {
            setStatus("closed");
          }
          reject(new Error("WebSocket 连接已关闭"));
        };
      });

      // Re-check after awaiting open
      if (!connectActiveRef.current) {
        return;
      }

      // Now that WS is open, set up the message handler
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as {
            action: string;
            code: string;
            data: string;
            desc: string;
          };

          if (msg.code !== "0") {
            setError(`讯飞 ASR 错误: ${msg.desc} (${msg.code})`);
            setStatus("error");
            ws.close();
            wsRef.current = null;
            return;
          }

          if (msg.action === "result" && msg.data) {
            const result = JSON.parse(msg.data) as IflytekResultData;
            const st = result.cn.st;

            const allCw = st.rt.flatMap((rt) => rt.ws).flatMap((ws) => ws.cw);
            const text = allCw.map((cw) => cw.w).join("");
            const isFinal = st.type === "0";

            if (isFinal) {
              const { segments: finalSegments, lastRole } = splitFinalWordsByRole(
                allCw,
                lastRoleRef.current
              );
              lastRoleRef.current = lastRole;
              setSegments((prev) => [...prev, ...finalSegments]);
              setPartialText("");
            } else {
              setPartialText(text);
            }
          }
        } catch {
          // Ignore parse errors for non-result messages
        }
      };

      // Update error/close handlers for the connected phase
      ws.onerror = () => {
        setError("WebSocket 连接错误");
        setStatus("error");
        ws.close();
        if (wsRef.current === ws) wsRef.current = null;
      };

      ws.onclose = () => {
        if (wsRef.current === ws) {
          setStatus("closed");
        }
      };
    } catch (err) {
      if (err instanceof Error && err.message === "ABORTED") {
        return; // disconnect() was called, silently abort
      }
      const msg = err instanceof Error ? err.message : "ASR 连接失败";
      setError(msg);
      setStatus("error");
    }
  }, []);

  const sendAudio = useCallback((chunk: ArrayBuffer) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(chunk);
    }
  }, []);

  /**
   * Send the iFlytek end-of-stream signal (`{end: true}`).
   * This forces the server to flush all buffered segments immediately.
   * Unlike disconnect(), this does NOT close the WebSocket or clear handlers,
   * so late segments can still arrive and be processed.
   */
  const sendEnd = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ end: true }));
    }
  }, []);

  const disconnect = useCallback(() => {
    connectActiveRef.current = false; // Cancel any in-flight connect() awaiting getAsrSignedUrl
    const ws = wsRef.current;
    if (ws) {
      // Send end signal per iFlytek protocol, then close
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ end: true }));
      }
      // Remove handlers to prevent stale state updates
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      // Close gracefully — for both OPEN and CONNECTING states
      if (ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        ws.close();
      }
      wsRef.current = null;
    }
    setStatus("closed");
  }, []);

  const reset = useCallback(() => {
    setSegments([]);
    setPartialText("");
    setError(null);
    lastRoleRef.current = 0;
  }, []);

  return {
    status,
    error,
    segments,
    partialText,
    connect,
    sendAudio,
    sendEnd,
    disconnect,
    reset,
  };
}
