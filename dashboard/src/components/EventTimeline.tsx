import StatusBadge from "./StatusBadge";
import type { PipelineEvent } from "@/lib/types";

function formatTime(timestamp: number): string {
  const d = new Date(timestamp);
  return d.toISOString().slice(11, 19) + " UTC";
}

interface EventTimelineProps {
  events: PipelineEvent[];
}

export default function EventTimeline({ events }: EventTimelineProps) {
  if (events.length === 0) {
    return <p className="text-sm text-gray-500 py-4">No events found</p>;
  }

  const sorted = [...events].sort((a, b) => b.timestamp - a.timestamp);

  return (
    <div className="divide-y divide-gray-200">
      {sorted.map((event, idx) => (
        <div
          key={`${event.timestamp}-${event.eventType}-${idx}`}
          className="flex items-start gap-3 py-3"
        >
          <span className="shrink-0 text-xs font-mono text-gray-500 pt-0.5">
            {formatTime(event.timestamp)}
          </span>
          <StatusBadge type={event.eventType} />
          <span className="text-sm text-gray-700 break-words min-w-0">
            {event.message}
          </span>
        </div>
      ))}
    </div>
  );
}
