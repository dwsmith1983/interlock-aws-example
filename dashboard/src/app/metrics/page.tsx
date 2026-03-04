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
  AreaChart,
  Area,
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
  if (red.has(type)) return "#f87171";
  if (yellow.has(type)) return "#fbbf24";
  if (green.has(type)) return "#34d399";
  return "#38bdf8";
}

const SLA_COLORS = ["#34d399", "#fbbf24", "#f87171"];

// ---------------------------------------------------------------------------
// Dark-themed chart props
// ---------------------------------------------------------------------------

const darkGrid = { stroke: "rgba(255,255,255,0.06)" };
const darkAxisLine = { stroke: "rgba(255,255,255,0.1)" };
const darkTick = { fill: "#94a3b8", fontSize: 11 };
const darkTooltip = {
  backgroundColor: "rgba(15,23,42,0.9)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  color: "#f0fdf4",
};

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
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl">
      <h3 className="mb-4 text-sm font-semibold text-slate-300">{title}</h3>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat card wrapper
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl">
      <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold text-emerald-300">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
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
      { name: "Met", value: data.sla.SLA_MET },
      { name: "Warning", value: data.sla.SLA_WARNING },
      { name: "Breach", value: data.sla.SLA_BREACH },
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

  const slaMet = data?.sla?.SLA_MET ?? 0;
  const slaWarning = data?.sla?.SLA_WARNING ?? 0;
  const slaBreach = data?.sla?.SLA_BREACH ?? 0;
  const slaTotal = slaMet + slaWarning + slaBreach;
  const slaMetRate = slaTotal === 0 ? 0 : Math.round((slaMet / slaTotal) * 100);

  const topEventType = useMemo(() => {
    if (byTypeData.length === 0) return "\u2014";
    return byTypeData[0].type;
  }, [byTypeData]);

  // --- Render ---------------------------------------------------------------

  const RANGES: DateRange[] = ["24h", "7d", "30d"];

  return (
    <div>
      <h1 className="text-2xl font-bold text-white">Metrics</h1>
      <p className="mt-1 text-sm text-slate-400">
        Event distribution and SLA compliance over time.
      </p>

      {/* Date range pills */}
      <div className="mt-6 flex gap-2">
        {RANGES.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-all ${
              range === r
                ? "border border-emerald-400/30 bg-emerald-500/20 text-emerald-300 shadow-[0_0_12px_rgba(52,211,153,0.15)]"
                : "border border-white/10 bg-white/[0.03] text-slate-400 backdrop-blur-xl hover:bg-white/[0.06] hover:text-slate-300"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Loading / Error */}
      {isLoading && (
        <p className="mt-6 text-sm text-slate-500">Loading metrics data...</p>
      )}
      {error && (
        <p className="mt-6 text-sm text-red-400">{error.message}</p>
      )}

      {!isLoading && !error && data && (
        <>
          {/* Summary stat cards */}
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="Total Events"
              value={totalEvents.toLocaleString()}
            />
            <StatCard
              label="SLA Met Rate"
              value={`${slaMetRate}%`}
              sub={`${slaMet} of ${slaTotal} executions`}
            />
            <StatCard label="Top Event Type" value={topEventType} />
          </div>

          {/* Charts 2x2 grid */}
          <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* 1. Events by Type — horizontal bar chart */}
            <ChartCard title="Events by Type">
              {byTypeData.length > 0 ? (
                <ResponsiveContainer
                  width="100%"
                  height={Math.max(250, byTypeData.length * 36)}
                >
                  <BarChart data={byTypeData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" {...darkGrid} />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tick={darkTick}
                      axisLine={darkAxisLine}
                    />
                    <YAxis
                      type="category"
                      dataKey="type"
                      width={160}
                      tick={darkTick}
                      axisLine={darkAxisLine}
                    />
                    <Tooltip contentStyle={darkTooltip} />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                      {byTypeData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-slate-600">
                  No event data available.
                </p>
              )}
            </ChartCard>

            {/* 2. SLA Compliance — donut chart */}
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
                      innerRadius={60}
                      outerRadius={80}
                      strokeWidth={0}
                    >
                      {slaData.map((entry, idx) => {
                        const colorIdx =
                          entry.name === "Met"
                            ? 0
                            : entry.name === "Warning"
                              ? 1
                              : 2;
                        return (
                          <Cell key={idx} fill={SLA_COLORS[colorIdx]} />
                        );
                      })}
                    </Pie>
                    <Tooltip contentStyle={darkTooltip} />
                    {/* Center label */}
                    <text
                      x="50%"
                      y="46%"
                      textAnchor="middle"
                      dominantBaseline="central"
                      className="text-2xl font-bold"
                      fill="#34d399"
                    >
                      {slaMetRate}%
                    </text>
                    <text
                      x="50%"
                      y="56%"
                      textAnchor="middle"
                      dominantBaseline="central"
                      className="text-xs"
                      fill="#94a3b8"
                    >
                      SLA met
                    </text>
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-slate-600">
                  No SLA data available.
                </p>
              )}
            </ChartCard>

            {/* 3. Events per Hour — area chart */}
            <ChartCard title="Events per Hour">
              {byHourData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={byHourData}>
                    <defs>
                      <linearGradient
                        id="emeraldGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="#34d399"
                          stopOpacity={0.3}
                        />
                        <stop
                          offset="100%"
                          stopColor="#34d399"
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" {...darkGrid} />
                    <XAxis
                      dataKey="hour"
                      tick={darkTick}
                      axisLine={darkAxisLine}
                      angle={-35}
                      textAnchor="end"
                      height={60}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={darkTick}
                      axisLine={darkAxisLine}
                    />
                    <Tooltip contentStyle={darkTooltip} />
                    <Area
                      type="monotone"
                      dataKey="count"
                      stroke="#34d399"
                      fill="url(#emeraldGradient)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-slate-600">
                  No hourly data available.
                </p>
              )}
            </ChartCard>

            {/* 4. Events by Pipeline — horizontal bar chart */}
            <ChartCard title="Events by Pipeline">
              {byPipelineData.length > 0 ? (
                <ResponsiveContainer
                  width="100%"
                  height={Math.max(250, byPipelineData.length * 40)}
                >
                  <BarChart data={byPipelineData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" {...darkGrid} />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tick={darkTick}
                      axisLine={darkAxisLine}
                    />
                    <YAxis
                      type="category"
                      dataKey="pipeline"
                      width={160}
                      tick={darkTick}
                      axisLine={darkAxisLine}
                    />
                    <Tooltip contentStyle={darkTooltip} />
                    <Bar
                      dataKey="count"
                      fill="#38bdf8"
                      radius={[0, 4, 4, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-12 text-center text-sm text-slate-600">
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
