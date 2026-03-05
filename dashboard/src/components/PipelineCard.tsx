import { severityOf, SEVERITY_COLORS } from "@/lib/events";
import StatusBadge from "./StatusBadge";
import type { PipelineSummary } from "@/lib/types";

interface Props {
  id: string;
  summary: PipelineSummary | undefined;
  selected: boolean;
  onClick: () => void;
}

export default function PipelineCard({ id, summary, selected, onClick }: Props) {
  const lastType = summary?.lastEvent?.eventType ?? "UNKNOWN";
  const sev = severityOf(lastType);
  const dotColor = SEVERITY_COLORS[sev];
  const count = summary?.events ?? 0;

  return (
    <button
      onClick={onClick}
      className={`
        flex flex-col gap-1.5 p-3 rounded-lg border text-left transition-all w-full
        ${selected
          ? "border-accent bg-accent/5 shadow-md ring-1 ring-accent/20"
          : "border-border bg-surface hover:border-accent/40 hover:shadow-sm"
        }
      `}
    >
      <div className="flex items-center gap-2">
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ backgroundColor: dotColor }}
        />
        <span className="text-sm font-medium text-text truncate">{id}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-muted">{count} events</span>
        {summary?.lastEvent && <StatusBadge type={summary.lastEvent.eventType} />}
      </div>
    </button>
  );
}
