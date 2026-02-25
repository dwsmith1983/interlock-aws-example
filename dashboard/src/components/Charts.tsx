"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import type { ChaosEvent, JobLog } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  COMPLETED: "#10b981",
  FAILED: "#ef4444",
  PENDING: "#f59e0b",
};

const CATEGORY_COLORS: Record<string, string> = {
  infrastructure: "#6366f1",
  "data plane": "#06b6d4",
  "data-plane": "#06b6d4",
  "control plane": "#8b5cf6",
  "control-plane": "#8b5cf6",
  cascade: "#f59e0b",
  evaluator: "#ec4899",
};

const CHAOS_STATUS_COLORS: Record<string, string> = {
  INJECTED: "#f97316",
  DETECTED: "#3b82f6",
  RECOVERED: "#10b981",
  UNRECOVERED: "#ef4444",
};

function bucketByHour(
  items: Array<{ timestamp?: string; injectedAt?: string }>,
  timeField: "timestamp" | "injectedAt" = "timestamp",
  hours = 24
): Array<Record<string, string | number>> {
  const now = Date.now();
  const buckets: Record<string, Record<string, number>> = {};

  for (let h = hours - 1; h >= 0; h--) {
    const key = new Date(now - h * 3600_000).toISOString().slice(0, 13);
    buckets[key] = {};
  }

  for (const item of items) {
    const ts = (item as Record<string, unknown>)[timeField] as string | undefined;
    if (!ts) continue;
    const key = ts.slice(0, 13);
    if (key in buckets) {
      const status =
        (item as Record<string, unknown>).status as string || "unknown";
      buckets[key][status] = (buckets[key][status] || 0) + 1;
    }
  }

  return Object.entries(buckets).map(([hour, counts]) => ({
    hour: hour.slice(11) + ":00",
    ...counts,
  }));
}

export function JobTimelineChart({ jobs }: { jobs: JobLog[] }) {
  const data = bucketByHour(jobs, "timestamp");

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        <Area
          type="monotone"
          dataKey="COMPLETED"
          stackId="1"
          stroke={STATUS_COLORS.COMPLETED}
          fill={STATUS_COLORS.COMPLETED}
          fillOpacity={0.6}
        />
        <Area
          type="monotone"
          dataKey="FAILED"
          stackId="1"
          stroke={STATUS_COLORS.FAILED}
          fill={STATUS_COLORS.FAILED}
          fillOpacity={0.6}
        />
        <Area
          type="monotone"
          dataKey="PENDING"
          stackId="1"
          stroke={STATUS_COLORS.PENDING}
          fill={STATUS_COLORS.PENDING}
          fillOpacity={0.6}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ChaosInjectionChart({ events }: { events: ChaosEvent[] }) {
  const data = bucketByHour(events, "injectedAt");

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        <Bar dataKey="INJECTED" fill={CHAOS_STATUS_COLORS.INJECTED} />
        <Bar dataKey="RECOVERED" fill={CHAOS_STATUS_COLORS.RECOVERED} />
        <Bar dataKey="UNRECOVERED" fill={CHAOS_STATUS_COLORS.UNRECOVERED} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ChaosRecoveryPie({ events }: { events: ChaosEvent[] }) {
  const counts: Record<string, number> = {};
  for (const e of events) {
    counts[e.status] = (counts[e.status] || 0) + 1;
  }

  const data = Object.entries(counts).map(([name, value]) => ({
    name,
    value,
  }));

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={80}
          paddingAngle={2}
          dataKey="value"
          label={({ name, value }) => `${name}: ${value}`}
        >
          {data.map((entry) => (
            <Cell
              key={entry.name}
              fill={CHAOS_STATUS_COLORS[entry.name] || "#94a3b8"}
            />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function CategoryBreakdownChart({
  events,
}: {
  events: ChaosEvent[];
}) {
  const categories: Record<string, { total: number; recovered: number }> = {};
  for (const e of events) {
    const cat = e.category || "unknown";
    if (!categories[cat]) categories[cat] = { total: 0, recovered: 0 };
    categories[cat].total++;
    if (e.status === "RECOVERED") categories[cat].recovered++;
  }

  const data = Object.entries(categories).map(([category, counts]) => ({
    category,
    total: counts.total,
    recovered: counts.recovered,
    rate: counts.total > 0 ? Math.round((counts.recovered / counts.total) * 100) : 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
        <YAxis
          type="category"
          dataKey="category"
          width={100}
          tick={{ fontSize: 11 }}
        />
        <Tooltip />
        <Legend />
        <Bar dataKey="total" fill="#6366f1" name="Total" />
        <Bar dataKey="recovered" fill="#10b981" name="Recovered" />
      </BarChart>
    </ResponsiveContainer>
  );
}
