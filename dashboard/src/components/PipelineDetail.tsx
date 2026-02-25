"use client";

import Link from "next/link";
import { usePipelineStatus, usePipelineJobs, usePipelineRunlogs } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { JobHistoryTable } from "@/components/JobHistoryTable";
import { JobTimelineChart } from "@/components/Charts";

export function PipelineDetail({ id }: { id: string }) {
  const { data: status, isLoading: statusLoading } = usePipelineStatus(id);
  const { data: jobData, isLoading: jobsLoading } = usePipelineJobs(id);
  const { data: runlogData } = usePipelineRunlogs(id);

  const isLoading = statusLoading || jobsLoading;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 animate-pulse rounded bg-gray-200" />
        <div className="h-48 animate-pulse rounded-lg bg-gray-200" />
        <div className="h-80 animate-pulse rounded-lg bg-gray-200" />
      </div>
    );
  }

  const jobs = jobData?.jobs || [];
  const runlogs = runlogData?.runlogs || [];

  function deriveHealth(): string {
    if (!status?.enabled) return "disabled";
    if ((status?.consecutiveFailures ?? 0) >= 3) return "failing";
    if ((status?.consecutiveFailures ?? 0) >= 1) return "degraded";
    return "healthy";
  }

  const health = deriveHealth();

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500">
        <Link href="/" className="hover:text-gray-700">
          Dashboard
        </Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900">{id}</span>
      </nav>

      {/* Status header */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{id}</h1>
            <p className="mt-1 text-sm text-gray-500">
              Pipeline health and run history
            </p>
          </div>
          <StatusBadge status={health} />
        </div>

        {status && (
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Last Status"
              value={status.lastStatus || "N/A"}
            />
            <StatCard
              label="Consecutive Failures"
              value={String(status.consecutiveFailures ?? 0)}
              highlight={
                (status.consecutiveFailures ?? 0) > 0 ? "red" : undefined
              }
            />
            <StatCard
              label="Last Success"
              value={formatTimestamp(status.lastSuccessfulRun)}
            />
            <StatCard
              label="Last Failure"
              value={formatTimestamp(status.lastFailedRun)}
              highlight={status.lastFailedRun ? "red" : undefined}
            />
          </div>
        )}
      </div>

      {/* Job timeline chart */}
      {jobs.length > 0 && (
        <section className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            Run Timeline (24h)
          </h2>
          <JobTimelineChart jobs={jobs} />
        </section>
      )}

      {/* Job history table */}
      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          Job History
        </h2>
        <JobHistoryTable jobs={jobs} />
      </section>

      {/* Recent runlogs */}
      {runlogs.length > 0 && (
        <section className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            Recent Run Logs
          </h2>
          <div className="space-y-2">
            {runlogs.slice(0, 20).map((rl, i) => (
              <div
                key={rl.SK || i}
                className="flex items-center justify-between rounded border border-gray-100 px-3 py-2 text-sm"
              >
                <span className="font-mono text-xs text-gray-500">
                  {rl.SK}
                </span>
                <span className="text-xs text-gray-400">
                  {rl.timestamp || ""}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: "red" | "green";
}) {
  const valueColor =
    highlight === "red"
      ? "text-red-600"
      : highlight === "green"
      ? "text-emerald-600"
      : "text-gray-900";

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
        {label}
      </p>
      <p className={`mt-1 text-lg font-semibold ${valueColor}`}>{value}</p>
    </div>
  );
}

function formatTimestamp(iso?: string): string {
  if (!iso) return "never";
  try {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ${mins % 60}m ago`;
    return d.toLocaleDateString();
  } catch {
    return iso;
  }
}
