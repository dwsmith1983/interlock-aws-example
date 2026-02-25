"use client";

import Link from "next/link";
import type { PipelineStatus } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

function deriveHealth(p: PipelineStatus): string {
  if (!p.enabled) return "disabled";
  if (p.consecutiveFailures >= 3) return "failing";
  if (p.consecutiveFailures >= 1) return "degraded";
  return "healthy";
}

function timeAgo(iso?: string): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const HEALTH_BORDER: Record<string, string> = {
  healthy: "border-l-emerald-500",
  degraded: "border-l-amber-500",
  failing: "border-l-red-500",
  disabled: "border-l-gray-400",
};

export function PipelineCard({ pipeline }: { pipeline: PipelineStatus }) {
  const health = deriveHealth(pipeline);
  const border = HEALTH_BORDER[health] || "border-l-gray-400";
  const lastRun = pipeline.lastSuccessfulRun || pipeline.lastFailedRun || pipeline.lastPendingRun;

  return (
    <Link href={`/pipeline/${pipeline.pipelineId}`}>
      <div
        className={`rounded-lg border border-l-4 ${border} bg-white p-4 shadow-sm transition hover:shadow-md`}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">
            {pipeline.pipelineId}
          </h3>
          <StatusBadge status={health} />
        </div>
        <div className="mt-3 space-y-1 text-sm text-gray-600">
          <div className="flex justify-between">
            <span>Last status</span>
            <span className="font-medium">
              {pipeline.lastStatus || "unknown"}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Last activity</span>
            <span>{timeAgo(lastRun)}</span>
          </div>
          <div className="flex justify-between">
            <span>Consecutive failures</span>
            <span
              className={
                pipeline.consecutiveFailures > 0
                  ? "font-medium text-red-600"
                  : ""
              }
            >
              {pipeline.consecutiveFailures}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
