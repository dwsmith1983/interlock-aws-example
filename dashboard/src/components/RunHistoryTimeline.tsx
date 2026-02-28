"use client";

import type { RunHistory } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

interface TimelineEntry {
  timestamp: string;
  kind: string;
  status?: string;
  message?: string;
  source: "event" | "alert" | "job";
}

const KIND_COLORS: Record<string, string> = {
  // Events
  TRAIT_EVALUATED: "bg-blue-500",
  READINESS_CHECKED: "bg-blue-500",
  RUN_STATE_CHANGED: "bg-emerald-500",
  TRIGGER_FIRED: "bg-indigo-500",
  SLA_BREACHED: "bg-red-500",
  RERUN_REQUESTED: "bg-amber-500",
  // Jobs
  STARTED: "bg-blue-500",
  COMPLETED: "bg-emerald-500",
  FAILED: "bg-red-500",
  ERROR: "bg-red-500",
  // Alerts
  alert: "bg-amber-500",
};

function getDotColor(kind: string, status?: string): string {
  if (status === "FAILED" || status === "ERROR") return "bg-red-500";
  if (status === "COMPLETED" || status === "READY") return "bg-emerald-500";
  if (status === "PENDING" || status === "NOT_READY") return "bg-amber-500";
  return KIND_COLORS[kind] || "bg-gray-400";
}

function formatDuration(startIso: string, endIso: string): string {
  try {
    const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
    if (ms < 0) return "N/A";
    const secs = Math.floor(ms / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    const remSecs = secs % 60;
    if (mins < 60) return `${mins}m ${remSecs}s`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ${mins % 60}m`;
  } catch {
    return "N/A";
  }
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function formatRelative(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return "";
  }
}

export function RunHistoryTimeline({ data }: { data: RunHistory }) {
  const runData = data.runLog?.runData || {};
  const status = (runData.status as string) || "UNKNOWN";
  const startedAt = runData.startedAt as string | undefined;
  const completedAt = runData.completedAt as string | undefined;
  const attemptNumber = (runData.attemptNumber as number) || 1;
  const retryHistory = (runData.retryHistory as Array<Record<string, unknown>>) || [];
  const failureMessage = runData.failureMessage as string | undefined;
  const failureCategory = runData.failureCategory as string | undefined;

  // Merge events, alerts, jobs into a unified timeline
  const entries: TimelineEntry[] = [];

  for (const evt of data.events || []) {
    // Events come from DynamoDB with extra fields (eventData, SK, PK)
    const raw = evt as unknown as Record<string, unknown>;
    const evtData = raw.eventData as Record<string, unknown> | undefined;
    entries.push({
      timestamp: evt.timestamp || (raw.SK as string) || "",
      kind: (evtData?.kind as string) || (evtData?.eventType as string) || "EVENT",
      status: (evtData?.status as string) || evt.status,
      message: (evtData?.message as string) || evt.message,
      source: "event",
    });
  }

  for (const alert of data.alerts || []) {
    entries.push({
      timestamp: alert.timestamp || "",
      kind: alert.alertType || "ALERT",
      status: alert.severity,
      message: alert.alertData?.message as string || alert.alertType,
      source: "alert",
    });
  }

  for (const job of data.jobs || []) {
    entries.push({
      timestamp: job.timestamp || "",
      kind: job.status || "JOB",
      status: job.status,
      message: `${job.stage} - ${job.status}`,
      source: "job",
    });
  }

  // Sort chronologically
  entries.sort((a, b) => {
    const ta = new Date(a.timestamp).getTime() || 0;
    const tb = new Date(b.timestamp).getTime() || 0;
    return ta - tb;
  });

  return (
    <div className="space-y-6">
      {/* Summary card */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {data.pipelineId}
            </h2>
            <p className="text-sm text-gray-500">
              {data.date} / {data.scheduleId}
            </p>
          </div>
          <StatusBadge status={status} />
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard label="Status" value={status} />
          <SummaryCard
            label="Duration"
            value={
              startedAt && completedAt
                ? formatDuration(startedAt, completedAt)
                : startedAt
                ? "In progress"
                : "Not started"
            }
          />
          <SummaryCard label="Attempts" value={String(attemptNumber)} />
          <SummaryCard
            label="Started"
            value={startedAt ? formatRelative(startedAt) : "N/A"}
          />
        </div>

        {failureMessage && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3">
            <p className="text-sm font-medium text-red-800">
              {failureCategory && (
                <span className="mr-2 rounded bg-red-200 px-1.5 py-0.5 text-xs font-semibold">
                  {failureCategory}
                </span>
              )}
              {failureMessage}
            </p>
          </div>
        )}
      </div>

      {/* Retry history */}
      {attemptNumber > 1 && retryHistory.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
            Retry History
          </h3>
          <div className="space-y-2">
            {retryHistory.map((attempt, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded border border-gray-100 bg-gray-50 px-3 py-2 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-700">
                    Attempt {(attempt.attemptNumber as number) || i + 1}
                  </span>
                  <StatusBadge
                    status={(attempt.status as string) || "UNKNOWN"}
                  />
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-500">
                  {typeof attempt.startedAt === "string" &&
                    typeof attempt.completedAt === "string" && (
                      <span>
                        {formatDuration(attempt.startedAt, attempt.completedAt)}
                      </span>
                    )}
                  {typeof attempt.failureMessage === "string" && (
                    <span className="text-red-600">
                      {attempt.failureMessage}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Event timeline */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Event Timeline ({entries.length})
        </h3>

        {entries.length === 0 ? (
          <p className="text-sm text-gray-400">
            No events found for this run.
          </p>
        ) : (
          <div className="relative">
            {/* Vertical line */}
            <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-gray-200" />

            <div className="space-y-3">
              {entries.map((entry, i) => (
                <div key={i} className="relative flex items-start gap-4 pl-8">
                  {/* Dot */}
                  <div
                    className={`absolute left-1.5 top-1.5 h-3 w-3 rounded-full ring-2 ring-white ${getDotColor(entry.kind, entry.status)}`}
                  />
                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center rounded bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-700">
                        {entry.kind}
                      </span>
                      {entry.status && <StatusBadge status={entry.status} />}
                      <span className="text-xs text-gray-400">
                        {entry.source}
                      </span>
                    </div>
                    {entry.message && (
                      <p className="mt-0.5 text-sm text-gray-600">
                        {entry.message}
                      </p>
                    )}
                  </div>
                  {/* Timestamp */}
                  <div className="shrink-0 text-right">
                    <p className="text-xs font-medium text-gray-600">
                      {formatTime(entry.timestamp)}
                    </p>
                    <p className="text-xs text-gray-400">
                      {formatRelative(entry.timestamp)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-gray-900">{value}</p>
    </div>
  );
}
