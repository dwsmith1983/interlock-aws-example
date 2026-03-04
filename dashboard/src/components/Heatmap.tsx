import type { PipelineEvent } from "@/lib/types";

const RED_TYPES = new Set([
  "SLA_BREACH", "JOB_FAILED", "INFRA_FAILURE", "SFN_TIMEOUT",
  "SCHEDULE_MISSED", "VALIDATION_EXHAUSTED", "RETRY_EXHAUSTED",
]);

interface HeatmapProps {
  events: PipelineEvent[];
  pipelines: string[];
  selectedHour?: string;
  selectedPipeline?: string;
  onSelectCell: (pipeline: string, hour: string) => void;
}

function cellColor(events: PipelineEvent[]): string {
  if (events.length === 0) return "rgba(255,255,255,0.03)";
  const hasCritical = events.some((e) => RED_TYPES.has(e.eventType));
  const count = events.length;
  if (hasCritical) {
    const opacity = Math.min(0.15 + count * 0.1, 0.6);
    return `rgba(248,113,113,${opacity})`;
  }
  const opacity = Math.min(0.1 + count * 0.08, 0.5);
  return `rgba(52,211,153,${opacity})`;
}

export default function Heatmap({ events, pipelines, selectedHour, selectedPipeline, onSelectCell }: HeatmapProps) {
  // Build grid: pipeline -> hour -> events[]
  const grid: Record<string, Record<string, PipelineEvent[]>> = {};
  for (const p of pipelines) {
    grid[p] = {};
    for (let h = 0; h < 24; h++) {
      grid[p][String(h).padStart(2, "0")] = [];
    }
  }
  for (const e of events) {
    const hour = String(new Date(e.timestamp).getUTCHours()).padStart(2, "0");
    if (grid[e.pipelineId]?.[hour]) {
      grid[e.pipelineId][hour].push(e);
    }
  }

  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[700px]">
        {/* Hour labels */}
        <div className="flex ml-32 mb-1">
          {hours.map((h) => (
            <div key={h} className="flex-1 text-center text-[10px] text-slate-500">{h}</div>
          ))}
        </div>
        {/* Rows */}
        {pipelines.map((pipeline) => (
          <div key={pipeline} className="flex items-center mb-1">
            <div className="w-32 text-xs text-slate-400 truncate pr-2 text-right">{pipeline}</div>
            <div className="flex flex-1 gap-0.5">
              {hours.map((hour) => {
                const cellEvents = grid[pipeline]?.[hour] ?? [];
                const isSelected = selectedPipeline === pipeline && selectedHour === hour;
                return (
                  <button
                    key={hour}
                    onClick={() => onSelectCell(pipeline, hour)}
                    className={`flex-1 h-7 rounded-sm transition-all ${
                      isSelected ? "ring-2 ring-white/50" : ""
                    }`}
                    style={{ backgroundColor: cellColor(cellEvents) }}
                    title={`${pipeline} T${hour}: ${cellEvents.length} events`}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
