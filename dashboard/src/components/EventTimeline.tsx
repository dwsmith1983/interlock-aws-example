import StatusBadge from "./StatusBadge";
import type { PipelineEvent } from "@/lib/types";

function formatTime(timestamp: number): string {
  return new Date(timestamp).toISOString().slice(11, 19) + " UTC";
}

export default function EventTimeline({ events }: { events: PipelineEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-500 py-4 text-center">Select a pipeline-hour from the heatmap</p>;
  }

  const sorted = [...events].sort((a, b) => b.timestamp - a.timestamp);

  return (
    <div className="space-y-2">
      {sorted.map((event, idx) => (
        <div key={`${event.timestamp}-${event.eventType}-${idx}`} className="flex items-start gap-3 py-2 border-b border-white/5 last:border-0">
          <span className="shrink-0 text-xs font-mono text-slate-500 pt-0.5">{formatTime(event.timestamp)}</span>
          <StatusBadge type={event.eventType} />
          <span className="text-sm text-slate-300 break-words min-w-0">{event.message}</span>
        </div>
      ))}
    </div>
  );
}
