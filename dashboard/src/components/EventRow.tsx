import { format } from "date-fns";
import { severityOf, SEVERITY_COLORS } from "@/lib/events";
import StatusBadge from "./StatusBadge";
import type { PipelineEvent } from "@/lib/types";

export default function EventRow({ event }: { event: PipelineEvent }) {
  const sev = severityOf(event.eventType);
  const dotColor = SEVERITY_COLORS[sev];
  const time = format(new Date(event.timestamp), "HH:mm:ss");

  return (
    <div className="flex items-center gap-3 py-2 px-3 border-b border-border last:border-0 hover:bg-background/50">
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: dotColor }}
      />
      <span className="text-xs text-text-muted w-16 shrink-0 font-mono">{time}</span>
      <span className="text-xs text-text-muted w-28 shrink-0 truncate">
        {event.pipelineId}
      </span>
      <StatusBadge type={event.eventType} />
      <span className="text-xs text-text-muted truncate">{event.message}</span>
    </div>
  );
}
