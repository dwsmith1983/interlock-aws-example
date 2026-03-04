"use client";

import { useState, useMemo } from "react";
import { useMetrics } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

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
// Color helpers
// ---------------------------------------------------------------------------

function eventColor(type: string): string {
  const red = new Set([
    "SLA_BREACH",
    "JOB_FAILED",
    "INFRA_FAILURE",
    "SFN_TIMEOUT",
    "SCHEDULE_MISSED",
    "VALIDATION_EXHAUSTED",
    "RETRY_EXHAUSTED",
  ]);
  const yellow = new Set(["SLA_WARNING"]);
  const green = new Set(["SLA_MET", "JOB_COMPLETED", "VALIDATION_PASSED"]);
  if (red.has(type)) return "#ef4444";
  if (yellow.has(type)) return "#eab308";
  if (green.has(type)) return "#22c55e";
  return "#3b82f6";
}

const SLA_COLORS = ["#22c55e", "#eab308", "#ef4444"];

// ---------------------------------------------------------------------------
// Pie label renderer
// ---------------------------------------------------------------------------

/* eslint-disable @typescript-eslint/no-explicit-any */
function renderPieLabel(props: any) {
  const { cx, cy, midAngle, innerRadius, outerRadius, percent, value, name } =
    props as {
      cx: number;
      cy: number;
      midAngle: number;
      innerRadius: number;
      outerRadius: number;
      percent: number;
      value: number;
      name: string;
    };
  const RADIAN = Math.PI / 180;
  const radius = innerRadius + (outerRadius - innerRadius) * 1.4;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  if (percent < 0.01) return null;
  const label = String(name).replace("SLA_", "");
  return (
    <text
      x={x}
      y={y}
      fill="#374151"
      textAnchor={x > cx ? "start" : "end"}
      dominantBaseline="central"
      className="text-xs"
    >
      {label}: {value} ({(percent * 100).toFixed(0)}%)
    </text>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ---------------------------------------------------------------------------
// Chart card wrapper
// ---------------------------------------------------------------------------

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">{title}</h3>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function MetricsPage() {
  const [range, setRange] = useState<DateRange>("7d");
  const { from, to } = rangeParams(range);
  const { data, error, isLoading } = useMetrics(from, to);

  // --- Derived chart data ---------------------------------------------------

  const byTypeData = useMemo(() => {
    if (!data?.byType) return [];
    return Object.entries(data.byType)
      .map(([type, count]) => ({ type, count, fill: eventColor(type) }))
      .sort((a, b) => b.count - a.count);
  }, [data]);

  const slaData = useMemo(() => {
    if (!data?.sla) return [];
    return [
      { name: "SLA_MET", value: data.sla.SLA_MET },
      { name: "SLA_WARNING", value: data.sla.SLA_WARNING },
      { name: "SLA_BREACH", value: data.sla.SLA_BREACH },
    ].filter((d) => d.value > 0);
  }, [data]);

  const byHourData = useMemo(() => {
    if (!data?.byHour) return [];
    return Object.entries(data.byHour)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([hour, count]) => ({ hour, count }));
  }, [data]);

  const byPipelineData = useMemo(() => {
    if (!data?.byPipeline) return [];
    return Object.entries(data.byPipeline)
      .map(([pipeline, count]) => ({ pipeline, count }))
      .sort((a, b) => b.count - a.count);
  }, [data]);

  // --- Summary stats --------------------------------------------------------

  const totalEvents = data?.totalEvents ?? 0;

  const slaMetRate = useMemo(() => {
    if (!data?.sla) return 0;
    const total = data.sla.SLA_MET + data.sla.SLA_WARNING + data.sla.SLA_BREACH;
    if (total === 0) return 0;
    return Math.round((data.sla.SLA_MET / total) * 100);
  }, [data]);

  const topEventType = useMemo(() => {
    if (byTypeData.length === 0) return "—";
    return byTypeData[0].type;
  }, [byTypeData]);

  // --- Render ---------------------------------------------------------------

  const RANGES: DateRange[] = ["24h", "7d", "30d"];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">Metrics</h1>
      <p className="mt-1 text-sm text-gray-600">
        Event distribution and SLA compliance over time.
      </p>

      {/* Date range selector */}
      <div className="mt-6">
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

      {/* Loading / Error */}
      {isLoading && (
        <p className="mt-4 text-sm text-gray-500">Loading metrics data...</p>
      )}
      {error && (
        <p className="mt-4 text-sm text-red-600">{error.message}</p>
      )}

      {!isLoading && !error && data && (
        <>
          {/* Summary stat cards */}
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg bg-white p-4 shadow">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                Total Events
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {totalEvents.toLocaleString()}
              </p>
            </div>
            <div className="rounded-lg bg-white p-4 shadow">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                SLA Met Rate
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {slaMetRate}%
              </p>
            </div>
            <div className="rounded-lg bg-white p-4 shadow">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                Top Event Type
              </p>
              <p className="mt-1 text-lg font-bold text-gray-900 truncate">
                {topEventType}
              </p>
            </div>
          </div>

          {/* Charts grid */}
          <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* 1. Event counts by type */}
            <ChartCard title="Event Counts by Type">
              {byTypeData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={byTypeData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="type"
                      tick={{ fontSize: 11 }}
                      angle={-35}
                      textAnchor="end"
                      height={80}
                    />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count">
                      {byTypeData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-gray-400">
                  No event data available.
                </p>
              )}
            </ChartCard>

            {/* 2. SLA compliance */}
            <ChartCard title="SLA Compliance">
              {slaData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={slaData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      label={renderPieLabel}
                    >
                      {slaData.map((entry, idx) => {
                        const colorIdx =
                          entry.name === "SLA_MET"
                            ? 0
                            : entry.name === "SLA_WARNING"
                              ? 1
                              : 2;
                        return (
                          <Cell key={idx} fill={SLA_COLORS[colorIdx]} />
                        );
                      })}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-gray-400">
                  No SLA data available.
                </p>
              )}
            </ChartCard>

            {/* 3. Events per hour */}
            <ChartCard title="Events per Hour">
              {byHourData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={byHourData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="hour"
                      tick={{ fontSize: 10 }}
                      angle={-35}
                      textAnchor="end"
                      height={80}
                    />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-gray-400">
                  No hourly data available.
                </p>
              )}
            </ChartCard>

            {/* 4. Events by pipeline (horizontal) */}
            <ChartCard title="Events by Pipeline">
              {byPipelineData.length > 0 ? (
                <ResponsiveContainer
                  width="100%"
                  height={Math.max(200, byPipelineData.length * 40)}
                >
                  <BarChart data={byPipelineData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis
                      type="category"
                      dataKey="pipeline"
                      width={140}
                      tick={{ fontSize: 12 }}
                    />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-gray-400">
                  No pipeline data available.
                </p>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}
