const RED_TYPES = new Set([
  "SLA_BREACH", "JOB_FAILED", "INFRA_FAILURE", "SFN_TIMEOUT",
  "SCHEDULE_MISSED", "VALIDATION_EXHAUSTED", "RETRY_EXHAUSTED",
]);
const YELLOW_TYPES = new Set(["SLA_WARNING"]);
const GREEN_TYPES = new Set(["SLA_MET", "JOB_COMPLETED", "VALIDATION_PASSED"]);

function colorClasses(type: string): string {
  if (RED_TYPES.has(type)) return "bg-red-500/20 text-[#f87171] border border-red-500/30";
  if (YELLOW_TYPES.has(type)) return "bg-amber-500/20 text-[#fbbf24] border border-amber-500/30";
  if (GREEN_TYPES.has(type)) return "bg-emerald-500/20 text-[#34d399] border border-emerald-500/30";
  return "bg-sky-500/20 text-[#38bdf8] border border-sky-500/30";
}

export default function StatusBadge({ type }: { type: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClasses(type)}`}>
      {type}
    </span>
  );
}
