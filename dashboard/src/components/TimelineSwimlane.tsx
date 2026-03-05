import { worstSeverity, SEVERITY_COLORS, type Severity } from "@/lib/events";
import type { PipelineEvent } from "@/lib/types";

interface Props {
  id: string;
  hours: Record<string, PipelineEvent[]>;
  nowHour: number;
  onCellClick?: (pipeline: string, hour: number) => void;
}

function countOpacity(count: number): number {
  if (count === 0) return 0;
  return Math.min(0.4 + count * 0.12, 1);
}

export default function TimelineSwimlane({ id, hours, nowHour, onCellClick }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted w-28 shrink-0 truncate text-right">
        {id}
      </span>
      <div className="grid grid-cols-24 gap-px flex-1">
        {Array.from({ length: 24 }, (_, h) => {
          const events = hours[String(h)] ?? [];
          const types = events.map((e) => e.eventType);
          const sev: Severity = events.length > 0 ? worstSeverity(types) : "info";
          const color = events.length > 0 ? SEVERITY_COLORS[sev] : "transparent";
          const opacity = countOpacity(events.length);
          const isNow = h === nowHour;

          return (
            <button
              key={h}
              onClick={() => onCellClick?.(id, h)}
              title={`${id} h${String(h).padStart(2, "0")} — ${events.length} events`}
              className={`h-7 rounded-sm transition-all hover:ring-1 hover:ring-accent/40 ${
                isNow ? "ring-1 ring-accent" : ""
              }`}
              style={{
                backgroundColor: events.length > 0 ? color : "#f1f5f9",
                opacity: events.length > 0 ? opacity : 1,
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
