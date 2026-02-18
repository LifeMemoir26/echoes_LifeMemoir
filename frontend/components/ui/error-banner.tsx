import { AlertOctagon, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  code: string;
  message: string;
  traceId?: string;
  retryable: boolean;
  onRetry?: () => void;
  retrying?: boolean;
};

export function ErrorBanner({ code, message, traceId, retryable, onRetry, retrying = false }: Props) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--accent-2)] bg-[color:color-mix(in_oklab,var(--accent-2)_14%,var(--bg-alt))] p-4">
      <div className="mb-2 flex items-start gap-2">
        <AlertOctagon className="mt-0.5 h-4 w-4 text-[var(--accent-2)]" />
        <div>
          <p className="text-sm font-medium text-[var(--fg)]">{message}</p>
          <p className="text-xs text-[var(--muted-fg)]">错误码: {code}</p>
          {traceId ? <p className="text-xs text-[var(--muted-fg)]">Trace: {traceId}</p> : null}
        </div>
      </div>
      {retryable && onRetry ? (
        <Button size="sm" onClick={onRetry} disabled={retrying}>
          <RotateCcw className="mr-2 h-3.5 w-3.5" />
          {retrying ? "重试中" : "重试生成"}
        </Button>
      ) : null}
    </div>
  );
}
