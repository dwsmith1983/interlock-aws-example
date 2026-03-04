"use client";

import { useState, useMemo } from "react";
import { useOverview, useEvents } from "@/lib/api";
import PipelineCard from "@/components/PipelineCard";
import StatusBadge from "@/components/StatusBadge";

const CDR_PIPELINES = ["bronze-cdr", "silver-cdr-hour", "silver-cdr-day"];
const SEQ_PIPELINES = ["bronze-seq", "silver-seq-hour", "silver-seq-day"];

const CRITICAL_TYPES = new Set([
  "SLA_BREACH", "JOB_FAILED", "INFRA_FAILURE", "SFN_TIMEOUT",
  "SCHEDULE_MISSED", "VALIDATION_EXHAUSTED", "RETRY_EXHAUSTED",
]);
const WARNING_TYPES = new Set(["SLA_WARNING"]);
const RECOVERY_TYPES = new Set(["SLA_MET", "JOB_COMPLETED", "VALIDATION_PASSED"]);

type Severity = "all" | "critical" | "warning" | "recovery";

function matchesSeverity(eventType: string, filter: Severity): boolean {
  if (filter === "all") return CRITICAL_TYPES.has(eventType) || WARNING_TYPES.has(eventType) || RECOVERY_TYPES.has(eventType);
  if (filter === "critical") return CRITICAL_TYPES.has(eventType);
  if (filter === "warning") return WARNING_TYPES.has(eventType);
  return RECOVERY_TYPES.has(eventType);
}

function formatTimestamp(ts: number): string {
  return new Date(ts).toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function severityDot(eventType: string): string {
  if (CRITICAL_TYPES.has(eventType)) return "bg-[#f87171]";
  if (WARNING_TYPES.has(eventType)) return "bg-[#fbbf24]";
  return "bg-[#34d399]";
}

export default function OverviewPage() {
  const { data, error, isLoading } = useOverview();
  const [alertFilter, setAlertFilter] = useState<Severity>("all");

  const now = Date.now();
  const { data: eventsData } = useEvents(undefined, now - 86400000, now);

  const filteredAlerts = useMemo(() => {
    if (!eventsData?.events) return [];
    return [...eventsData.events]
      .filter((e) => matchesSeverity(e.eventType, alertFilter))
      .sort((a, b) => b.timestamp - a.timestamp)
      .slice(0, 50);
  }, [eventsData, alertFilter]);

  const pipelines = data?.pipelines ?? {};

  const FILTERS: { key: Severity; label: string }[] = [
    { key: "all", label: "All" },
    { key: "critical", label: "Critical" },
    { key: "warning", label: "Warning" },
    { key: "recovery", label: "Recovery" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-white">Pipeline Overview</h1>

      {isLoading && <p className="mt-2 text-slate-400">Loading...</p>}
      {error && <p className="mt-2 text-[#f87171]">{error.message}</p>}

      {!isLoading && !error && (
        <>
          {/* Pipeline Status Grid */}
          <section className="mt-6">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">CDR Pipelines</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {CDR_PIPELINES.map((id) => {
                const summary = pipelines[id];
                if (!summary) return null;
                return <PipelineCard key={id} name={id} summary={summary} />;
              })}
            </div>
          </section>

          <section className="mt-6">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">SEQ Pipelines</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {SEQ_PIPELINES.map((id) => {
                const summary = pipelines[id];
                if (!summary) return null;
                return <PipelineCard key={id} name={id} summary={summary} />;
              })}
            </div>
          </section>

          {/* Recent Alerts Feed */}
          <section className="mt-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Recent Alerts</h2>
              <div className="flex gap-1">
                {FILTERS.map((f) => (
                  <button
                    key={f.key}
                    onClick={() => setAlertFilter(f.key)}
                    className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                      alertFilter === f.key
                        ? "bg-white/10 text-white border border-white/20"
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="glass p-4 max-h-96 overflow-y-auto space-y-2">
              {filteredAlerts.length === 0 ? (
                <p className="text-sm text-slate-500 py-4 text-center">No events match the current filter.</p>
              ) : (
                filteredAlerts.map((event, idx) => (
                  <div key={`${event.timestamp}-${idx}`} className="flex items-center gap-3 py-2 border-b border-white/5 last:border-0">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${severityDot(event.eventType)}`} />
                    <span className="text-xs font-mono text-slate-500 shrink-0">{formatTimestamp(event.timestamp)}</span>
                    <span className="text-xs text-slate-400 shrink-0">{event.pipelineId}</span>
                    <StatusBadge type={event.eventType} />
                    <span className="text-xs text-slate-400 truncate">{event.message}</span>
                  </div>
                ))
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
