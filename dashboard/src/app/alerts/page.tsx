"use client";

import { useState, useMemo } from "react";
import { useEvents } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";

// ---------------------------------------------------------------------------
// Severity categories
// ---------------------------------------------------------------------------

const CRITICAL_TYPES = new Set([
  "SLA_BREACH",
  "JOB_FAILED",
  "INFRA_FAILURE",
  "SFN_TIMEOUT",
  "SCHEDULE_MISSED",
  "VALIDATION_EXHAUSTED",
  "RETRY_EXHAUSTED",
]);

const WARNING_TYPES = new Set(["SLA_WARNING"]);

const RECOVERY_TYPES = new Set([
  "SLA_MET",
  "JOB_COMPLETED",
  "VALIDATION_PASSED",
]);

type Severity = "critical" | "warning" | "recovery";

function severity(eventType: string): Severity | null {
  if (CRITICAL_TYPES.has(eventType)) return "critical";
  if (WARNING_TYPES.has(eventType)) return "warning";
  if (RECOVERY_TYPES.has(eventType)) return "recovery";
  return null;
}

// ---------------------------------------------------------------------------
// Date range helpers
// ---------------------------------------------------------------------------

type DateRange = "24h" | "7d" | "30d";

const RANGE_MS: Record<DateRange, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

function rangeParams(range: DateRange): { from: number; to: number } {
  const now = Date.now();
  return { from: now - RANGE_MS[range], to: now };
}

// ---------------------------------------------------------------------------
// Row background by severity
// ---------------------------------------------------------------------------

const ROW_BG: Record<Severity, string> = {
  critical: "bg-red-50",
  warning: "bg-yellow-50",
  recovery: "bg-green-50",
};

// ---------------------------------------------------------------------------
// Timestamp formatter
// ---------------------------------------------------------------------------

function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function AlertsPage() {
  const [range, setRange] = useState<DateRange>("24h");
  const [filters, setFilters] = useState<Record<Severity, boolean>>({
    critical: true,
    warning: true,
    recovery: true,
  });

  const { from, to } = rangeParams(range);
  const { data, error, isLoading } = useEvents(undefined, from, to);

  const filteredEvents = useMemo(() => {
    if (!data?.events) return [];
    return [...data.events]
      .filter((e) => {
        const sev = severity(e.eventType);
        return sev !== null && filters[sev];
      })
      .sort((a, b) => b.timestamp - a.timestamp);
  }, [data, filters]);

  function toggleFilter(sev: Severity) {
    setFilters((prev) => ({ ...prev, [sev]: !prev[sev] }));
  }

  const RANGES: DateRange[] = ["24h", "7d", "30d"];

  const TOGGLE_META: { key: Severity; label: string; onClass: string; offClass: string }[] = [
    {
      key: "critical",
      label: "Critical",
      onClass: "bg-red-600 text-white",
      offClass: "bg-gray-200 text-gray-600 hover:bg-gray-300",
    },
    {
      key: "warning",
      label: "Warning",
      onClass: "bg-yellow-500 text-white",
      offClass: "bg-gray-200 text-gray-600 hover:bg-gray-300",
    },
    {
      key: "recovery",
      label: "Recovery",
      onClass: "bg-green-600 text-white",
      offClass: "bg-gray-200 text-gray-600 hover:bg-gray-300",
    },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">Alerts</h1>
      <p className="mt-1 text-sm text-gray-600">
        Pipeline events filtered by severity and date range.
      </p>

      {/* Controls */}
      <div className="mt-6 flex flex-wrap items-end gap-6">
        {/* Severity toggles */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Severity
          </label>
          <div className="flex gap-1">
            {TOGGLE_META.map((t) => (
              <button
                key={t.key}
                onClick={() => toggleFilter(t.key)}
                className={`px-3 py-1.5 text-sm font-medium rounded transition-colors ${
                  filters[t.key] ? t.onClass : t.offClass
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Date range selector */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Date Range
          </label>
          <div className="flex gap-1">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-3 py-1.5 text-sm font-medium rounded ${
                  range === r
                    ? "bg-gray-900 text-white"
                    : "bg-gray-200 text-gray-700 hover:bg-gray-300"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Results summary */}
      <p className="mt-4 text-sm text-gray-500">
        {isLoading
          ? "Loading events..."
          : error
            ? ""
            : `${filteredEvents.length} event${filteredEvents.length !== 1 ? "s" : ""}`}
      </p>

      {/* Error state */}
      {error && (
        <p className="mt-2 text-sm text-red-600">{error.message}</p>
      )}

      {/* Desktop table */}
      {!isLoading && !error && filteredEvents.length > 0 && (
        <>
          <div className="mt-4 hidden sm:block overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-300 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  <th className="py-2 pr-4">Timestamp</th>
                  <th className="py-2 pr-4">Pipeline</th>
                  <th className="py-2 pr-4">Event Type</th>
                  <th className="py-2">Message</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredEvents.map((event, idx) => {
                  const sev = severity(event.eventType);
                  const bg = sev ? ROW_BG[sev] : "";
                  return (
                    <tr
                      key={`${event.timestamp}-${event.eventType}-${idx}`}
                      className={bg}
                    >
                      <td className="py-2 pr-4 font-mono text-xs text-gray-600 whitespace-nowrap">
                        {formatTimestamp(event.timestamp)}
                      </td>
                      <td className="py-2 pr-4 text-gray-900 whitespace-nowrap">
                        {event.pipelineId}
                      </td>
                      <td className="py-2 pr-4">
                        <StatusBadge type={event.eventType} />
                      </td>
                      <td className="py-2 text-gray-700 break-words max-w-md">
                        {event.message}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="mt-4 sm:hidden space-y-3">
            {filteredEvents.map((event, idx) => {
              const sev = severity(event.eventType);
              const bg = sev ? ROW_BG[sev] : "bg-white";
              return (
                <div
                  key={`${event.timestamp}-${event.eventType}-${idx}`}
                  className={`rounded-lg border border-gray-200 p-3 ${bg}`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <StatusBadge type={event.eventType} />
                    <span className="text-xs font-mono text-gray-500">
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-gray-900">
                    {event.pipelineId}
                  </p>
                  <p className="mt-1 text-sm text-gray-700 break-words">
                    {event.message}
                  </p>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Empty state */}
      {!isLoading && !error && filteredEvents.length === 0 && (
        <p className="mt-4 text-sm text-gray-500 py-4">
          No events match the current filters.
        </p>
      )}
    </div>
  );
}
