import { ApiRequestError, getApiBaseUrl, getAuthHeaders, parseEnvelope } from "@/lib/api/client";
import type { InterviewSseEnvelope, InterviewSseEventType } from "@/lib/api/types";

const VALID_EVENTS: InterviewSseEventType[] = ["connected", "heartbeat", "status", "context", "error", "completed"];

type ConnectOptions = {
  sessionId: string;
  lastEventId?: string;
  signal?: AbortSignal;
};

export type InterviewSseHandle = {
  close: () => void;
  done: Promise<void>;
};

function parseRawSseChunk(rawBlock: string): { id: string; event: string; data: string } | null {
  const lines = rawBlock.split(/\r?\n/);
  let id = "";
  let event = "message";
  const dataParts: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("id:")) {
      id = line.slice(3).trim();
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataParts.push(line.slice(5).trim());
    }
  }

  if (!dataParts.length) {
    return null;
  }

  return { id, event, data: dataParts.join("\n") };
}

function isInterviewEvent(event: string): event is InterviewSseEventType {
  return VALID_EVENTS.includes(event as InterviewSseEventType);
}

export async function connectInterviewSse(
  options: ConnectOptions,
  onEvent: (event: InterviewSseEnvelope) => void
): Promise<InterviewSseHandle> {
  const controller = new AbortController();
  const signal = options.signal;

  if (signal?.aborted) {
    controller.abort();
  } else if (signal) {
    signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let headers: HeadersInit = { Accept: "text/event-stream", ...getAuthHeaders() };
  if (options.lastEventId) {
    headers = { ...headers, "Last-Event-ID": options.lastEventId };
  }

  const response = await fetch(`${getApiBaseUrl()}/session/${options.sessionId}/events`, {
    method: "GET",
    headers,
    signal: controller.signal
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    if (text) {
      let parsed: ReturnType<typeof parseEnvelope<Record<string, unknown>>> | null = null;
      try {
        parsed = parseEnvelope<Record<string, unknown>>(JSON.parse(text));
      } catch {
        parsed = null;
      }
      const first = parsed?.errors[0];
      if (first) {
        throw new ApiRequestError({
          code: first.error_code,
          message: first.error_message,
          retryable: first.retryable,
          traceId: first.trace_id,
          details: first.error_details
        });
      }
    }

    throw new ApiRequestError({
      code: "SSE_CONNECT_FAILED",
      message: `SSE 连接失败（HTTP ${response.status}）`,
      retryable: response.status >= 500
    });
  }

  const done = (async () => {
    const reader = response.body!.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    try {
      while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          const parsed = parseRawSseChunk(chunk.trim());
          if (!parsed || !isInterviewEvent(parsed.event)) {
            continue;
          }

          let payload: unknown;
          try {
            payload = JSON.parse(parsed.data);
          } catch {
            continue;
          }

          onEvent({
            id: parsed.id,
            event: parsed.event,
            data: payload as InterviewSseEnvelope["data"]
          });
        }
      }
    } finally {
      reader.releaseLock();
    }
  })();

  return {
    close: () => controller.abort(),
    done
  };
}
