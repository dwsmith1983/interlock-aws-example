import { severityOf, SEVERITY_BG } from "@/lib/events";

export default function StatusBadge({ type }: { type: string }) {
  const sev = severityOf(type);
  const bg = SEVERITY_BG[sev];
  const label = type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${bg}`}>
      {label}
    </span>
  );
}
