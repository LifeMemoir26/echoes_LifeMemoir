import type { InterviewMessage } from "./interview-message-types";

export type MergedInterviewMessage = InterviewMessage & { count: number };

/** Group consecutive same-speaker messages into merged entries for display. */
export function mergeConsecutiveMessages(msgs: InterviewMessage[]): MergedInterviewMessage[] {
  const result: MergedInterviewMessage[] = [];

  for (const msg of msgs) {
    const last = result[result.length - 1];
    if (last && last.role === msg.role) {
      last.content += msg.content;
      last.count += 1;
    } else {
      result.push({ ...msg, count: 1 });
    }
  }

  return result;
}
