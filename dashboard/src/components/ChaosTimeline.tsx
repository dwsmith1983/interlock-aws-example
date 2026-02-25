"use client";

import type { ChaosEvent } from "@/lib/types";
import { StatusBadge, SeverityBadge } from "./StatusBadge";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function elapsedTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

export function ChaosTimeline({ events }: { events: ChaosEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-500">
        No chaos events recorded
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {events.map((event, i) => (
        <div
          key={event.SK || i}
          className="flex items-start gap-3 rounded-lg border bg-white p-3"
        >
          <div className="mt-0.5">
            <ChaosIcon status={event.status} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-gray-900">
                {event.scenario}
              </span>
              <StatusBadge status={event.status} />
              <SeverityBadge severity={event.severity} />
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-gray-500">
              <span>Target: {event.target}</span>
              <span>Category: {event.category}</span>
              <span>Injected: {timeAgo(event.injectedAt)}</span>
              {event.status === "INJECTED" && (
                <span className="text-orange-600">
                  Elapsed: {elapsedTime(event.injectedAt)}
                </span>
              )}
              {event.recoveredAt && (
                <span className="text-emerald-600">
                  Recovered: {timeAgo(event.recoveredAt)}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ChaosIcon({ status }: { status: string }) {
  const colors: Record<string, string> = {
    INJECTED: "text-orange-500",
    DETECTED: "text-blue-500",
    RECOVERED: "text-emerald-500",
    UNRECOVERED: "text-red-500",
  };
  const color = colors[status] || "text-gray-400";

  return (
    <svg
      className={`h-5 w-5 ${color}`}
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M11.42 15.17l-5.59-6.6a1.5 1.5 0 010-1.94l5.59-6.6a1.5 1.5 0 012.16 0l5.59 6.6a1.5 1.5 0 010 1.94l-5.59 6.6a1.5 1.5 0 01-2.16 0z"
      />
    </svg>
  );
}
