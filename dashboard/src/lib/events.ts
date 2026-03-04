export const FAILURE_TYPES = new Set([
  "SLA_BREACH", "JOB_FAILED", "INFRA_FAILURE", "SFN_TIMEOUT",
  "SCHEDULE_MISSED", "VALIDATION_EXHAUSTED", "RETRY_EXHAUSTED",
]);

export const WARNING_TYPES = new Set(["SLA_WARNING"]);

export const SUCCESS_TYPES = new Set(["SLA_MET", "JOB_COMPLETED", "VALIDATION_PASSED"]);

export type Severity = "critical" | "warning" | "success" | "info";

export function severityOf(type: string): Severity {
  if (FAILURE_TYPES.has(type)) return "critical";
  if (WARNING_TYPES.has(type)) return "warning";
  if (SUCCESS_TYPES.has(type)) return "success";
  return "info";
}

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "#f87171",
  warning: "#fbbf24",
  success: "#34d399",
  info: "#38bdf8",
};

export function eventColor(type: string): string {
  return SEVERITY_COLORS[severityOf(type)];
}
