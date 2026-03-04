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

function colorClasses(type: string): string {
  if (RED_TYPES.has(type)) return "bg-red-100 text-red-800";
  if (YELLOW_TYPES.has(type)) return "bg-yellow-100 text-yellow-800";
  if (GREEN_TYPES.has(type)) return "bg-green-100 text-green-800";
  return "bg-blue-100 text-blue-800";
}

export default function StatusBadge({ type }: { type: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colorClasses(type)}`}
    >
      {type}
    </span>
  );
}
