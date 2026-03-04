import { severityOf } from "@/lib/events";
import type { Severity } from "@/lib/events";

const BADGE_CLASSES: Record<Severity, string> = {
  critical: "bg-red-500/20 text-[#f87171] border border-red-500/30",
  warning: "bg-amber-500/20 text-[#fbbf24] border border-amber-500/30",
  success: "bg-emerald-500/20 text-[#34d399] border border-emerald-500/30",
  info: "bg-sky-500/20 text-[#38bdf8] border border-sky-500/30",
};

export default function StatusBadge({ type }: { type: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_CLASSES[severityOf(type)]}`}>
      {type}
    </span>
  );
}
