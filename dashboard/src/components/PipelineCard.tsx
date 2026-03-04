import StatusBadge from "./StatusBadge";
import type { PipelineSummary } from "@/lib/types";

const FAILURE_TYPES = new Set([
  "SLA_BREACH",
  "JOB_FAILED",
  "INFRA_FAILURE",
  "SFN_TIMEOUT",
  "SCHEDULE_MISSED",
  "VALIDATION_EXHAUSTED",
  "RETRY_EXHAUSTED",
]);

function borderColor(eventType: string | undefined): string {
  if (!eventType) return "border-gray-300";
  if (FAILURE_TYPES.has(eventType)) return "border-red-500";
  if (eventType === "SLA_WARNING") return "border-yellow-500";
  if (eventType === "SLA_MET" || eventType === "JOB_COMPLETED") return "border-green-500";
  return "border-gray-300";
}

function timeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

interface Props {
  name: string;
  summary: PipelineSummary;
}

export default function PipelineCard({ name, summary }: Props) {
  const lastType = summary.lastEvent?.eventType;

  return (
    <div
      className={`rounded-lg border-l-4 bg-white p-4 shadow-sm ${borderColor(lastType)}`}
    >
      <h3 className="text-sm font-semibold text-gray-900">{name}</h3>
      <p className="mt-1 text-xs text-gray-500">
        {summary.events} event{summary.events !== 1 ? "s" : ""} in last 24h
      </p>
      {summary.lastEvent ? (
        <div className="mt-2 flex items-center gap-2">
          <StatusBadge type={summary.lastEvent.eventType} />
          <span className="text-xs text-gray-400">
            {timeAgo(summary.lastEvent.timestamp)}
          </span>
        </div>
      ) : (
        <p className="mt-2 text-xs text-gray-400">No recent events</p>
      )}
    </div>
  );
}
