import type { EventSupplementItem, PendingEventDetail } from "@/lib/api/types";
import { Card } from "@/components/ui/card";
import { BackgroundSupplementPanel } from "./background-supplement-panel";
import { EmotionalAnchorsPanel } from "./emotional-anchors-panel";
import { PendingEventsPanel } from "./pending-events-panel";

export function InterviewSidePanels({
  isConnected,
  supplementsLoaded,
  pendingEventsLoaded,
  anchorsLoaded,
  supplements,
  pendingEvents,
  expandedIds,
  positiveTriggers,
  sensitiveTopics,
  onToggle,
  onTogglePriority,
}: {
  isConnected: boolean;
  supplementsLoaded: boolean;
  pendingEventsLoaded: boolean;
  anchorsLoaded: boolean;
  supplements: EventSupplementItem[];
  pendingEvents: PendingEventDetail[];
  expandedIds: Set<string>;
  positiveTriggers: string[];
  sensitiveTopics: string[];
  onToggle: (id: string) => void;
  onTogglePriority: (id: string) => void;
}) {
  return (
    <div className="grid flex-1 grid-cols-2 grid-rows-2 gap-4 overflow-hidden p-6">
      <Card className="row-span-2 min-h-0 overflow-hidden p-5">
        {isConnected && !supplementsLoaded ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-400">加载中…</div>
        ) : (
          <BackgroundSupplementPanel supplements={supplements} />
        )}
      </Card>

      <Card className="min-h-0 overflow-hidden p-5">
        {isConnected && !pendingEventsLoaded ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-400">加载中…</div>
        ) : (
          <PendingEventsPanel events={pendingEvents} expandedIds={expandedIds} onToggle={onToggle} onTogglePriority={onTogglePriority} />
        )}
      </Card>

      <Card className="min-h-0 overflow-hidden p-5">
        {isConnected && !anchorsLoaded ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-400">加载中…</div>
        ) : (
          <EmotionalAnchorsPanel positiveTriggers={positiveTriggers} sensitiveTopics={sensitiveTopics} />
        )}
      </Card>
    </div>
  );
}
