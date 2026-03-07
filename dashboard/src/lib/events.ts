export const FAILURE_TYPES = new Set([
  "SLA_BREACH", "JOB_FAILED", "INFRA_FAILURE", "SFN_TIMEOUT",
  "SCHEDULE_MISSED", "VALIDATION_EXHAUSTED", "RETRY_EXHAUSTED",
  "JOB_POLL_EXHAUSTED", "DATA_DRIFT",
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
  critical: "#ef4444",
  warning: "#f59e0b",
  success: "#10b981",
  info: "#6366f1",
};

export const SEVERITY_BG: Record<Severity, string> = {
  critical: "bg-failure/10 text-failure",
  warning: "bg-warning/10 text-warning",
  success: "bg-success/10 text-success",
  info: "bg-accent/10 text-accent",
};

export function eventColor(type: string): string {
  return SEVERITY_COLORS[severityOf(type)];
}

export function worstSeverity(types: string[]): Severity {
  if (types.some((t) => FAILURE_TYPES.has(t))) return "critical";
  if (types.some((t) => WARNING_TYPES.has(t))) return "warning";
  if (types.some((t) => SUCCESS_TYPES.has(t))) return "success";
  return "info";
}
