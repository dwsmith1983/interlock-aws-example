import type { PipelineEvent } from "@/lib/types";

const RED_TYPES = new Set([
  "SLA_BREACH",
  "JOB_FAILED",
  "INFRA_FAILURE",
  "SFN_TIMEOUT",
  "SCHEDULE_MISSED",
  "VALIDATION_EXHAUSTED",
  "RETRY_EXHAUSTED",
]);

const YELLOW_TYPES = new Set(["SLA_WARNING"]);

const GREEN_TYPES = new Set(["SLA_MET", "JOB_COMPLETED", "VALIDATION_PASSED"]);

function worstColor(events: PipelineEvent[]): "red" | "yellow" | "green" | "gray" {
  let hasYellow = false;
  let hasGreen = false;

  for (const e of events) {
    if (RED_TYPES.has(e.eventType)) return "red";
    if (YELLOW_TYPES.has(e.eventType)) hasYellow = true;
    if (GREEN_TYPES.has(e.eventType)) hasGreen = true;
  }

  if (hasYellow) return "yellow";
  if (hasGreen) return "green";
  return "gray";
}

const COLOR_CLASSES: Record<string, string> = {
  red: "bg-red-100 text-red-800 hover:bg-red-200",
  yellow: "bg-yellow-100 text-yellow-800 hover:bg-yellow-200",
  green: "bg-green-100 text-green-800 hover:bg-green-200",
  gray: "bg-gray-100 text-gray-400 hover:bg-gray-200",
};

interface HourGridProps {
  events: PipelineEvent[];
  selectedHour: string | undefined;
  onSelectHour: (hour: string | undefined) => void;
}

export default function HourGrid({ events, selectedHour, onSelectHour }: HourGridProps) {
  // Group events by UTC hour
  const byHour: Record<string, PipelineEvent[]> = {};
  for (let h = 0; h < 24; h++) {
    byHour[String(h).padStart(2, "0")] = [];
  }
  for (const e of events) {
    const hour = String(new Date(e.timestamp).getUTCHours()).padStart(2, "0");
    byHour[hour]?.push(e);
  }

  const hours = Object.keys(byHour).sort();

  return (
    <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
      {hours.map((hour) => {
        const color = worstColor(byHour[hour]);
        const isSelected = selectedHour === hour;

        return (
          <button
            key={hour}
            onClick={() => onSelectHour(isSelected ? undefined : hour)}
            className={`flex items-center justify-center rounded-lg py-3 text-sm font-medium transition-colors ${COLOR_CLASSES[color]} ${
              isSelected ? "ring-2 ring-gray-900 ring-offset-1" : ""
            }`}
          >
            {hour}
          </button>
        );
      })}
    </div>
  );
}
