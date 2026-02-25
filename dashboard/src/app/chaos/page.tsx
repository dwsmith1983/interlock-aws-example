"use client";

import { useChaosEvents, useChaosConfig } from "@/lib/api";
import { ChaosTimeline } from "@/components/ChaosTimeline";
import { StatusBadge, SeverityBadge } from "@/components/StatusBadge";
import {
  ChaosInjectionChart,
  ChaosRecoveryPie,
  CategoryBreakdownChart,
} from "@/components/Charts";

export default function ChaosPage() {
  const { data: eventData, isLoading: eventsLoading } = useChaosEvents();
  const { data: config, isLoading: configLoading } = useChaosConfig();

  if (eventsLoading || configLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-200" />
        <div className="h-16 animate-pulse rounded-lg bg-gray-200" />
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="h-80 animate-pulse rounded-lg bg-gray-200" />
          <div className="h-80 animate-pulse rounded-lg bg-gray-200" />
        </div>
      </div>
    );
  }

  const events = eventData?.events || [];
  const activeEvents = events.filter((e) => e.status === "INJECTED");
  const recoveredEvents = events.filter((e) => e.status === "RECOVERED");
  const unrecoveredEvents = events.filter((e) => e.status === "UNRECOVERED");
  const recoveryRate =
    events.length > 0
      ? Math.round((recoveredEvents.length / events.length) * 100)
      : 0;

  // Build scenario breakdown
  const scenarioMap: Record<
    string,
    { hits: number; recovered: number; totalRecoveryMs: number }
  > = {};
  for (const e of events) {
    if (!scenarioMap[e.scenario]) {
      scenarioMap[e.scenario] = { hits: 0, recovered: 0, totalRecoveryMs: 0 };
    }
    scenarioMap[e.scenario].hits++;
    if (e.status === "RECOVERED") {
      scenarioMap[e.scenario].recovered++;
      if (e.recoveredAt && e.injectedAt) {
        const ms =
          new Date(e.recoveredAt).getTime() -
          new Date(e.injectedAt).getTime();
        scenarioMap[e.scenario].totalRecoveryMs += ms;
      }
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Chaos Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Chaos injection tracking, recovery monitoring, and scenario analysis
        </p>
      </div>

      {/* Config banner */}
      <div
        className={`rounded-lg border p-4 ${
          config?.enabled
            ? "border-orange-200 bg-orange-50"
            : "border-gray-200 bg-gray-50"
        }`}
      >
        <div className="flex flex-wrap items-center gap-4">
          <span className="font-medium text-gray-900">
            Chaos:{" "}
            <StatusBadge
              status={config?.enabled ? "INJECTED" : "disabled"}
            />
          </span>
          {config?.severity && (
            <span>
              Severity: <SeverityBadge severity={config.severity} />
            </span>
          )}
          <span className="text-sm text-gray-600">
            Scenarios: <strong>{config?.scenarios?.length || 0}</strong>
          </span>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-4">
        <StatBox label="Total Events" value={events.length} />
        <StatBox
          label="Active"
          value={activeEvents.length}
          color="text-orange-600"
        />
        <StatBox
          label="Recovered"
          value={recoveredEvents.length}
          color="text-emerald-600"
        />
        <StatBox
          label="Recovery Rate"
          value={`${recoveryRate}%`}
          color={recoveryRate >= 80 ? "text-emerald-600" : "text-amber-600"}
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            Injection Timeline (24h)
          </h2>
          <ChaosInjectionChart events={events} />
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            Recovery Status
          </h2>
          <ChaosRecoveryPie events={events} />
        </section>
      </div>

      {/* Category breakdown */}
      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          Category Breakdown
        </h2>
        <CategoryBreakdownChart events={events} />
      </section>

      {/* Active injections */}
      {activeEvents.length > 0 && (
        <section className="rounded-lg border border-orange-200 bg-orange-50 p-6">
          <h2 className="mb-4 text-lg font-semibold text-orange-800">
            Active Injections ({activeEvents.length})
          </h2>
          <ChaosTimeline events={activeEvents} />
        </section>
      )}

      {/* Scenario breakdown table */}
      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          Scenario Breakdown
        </h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">
                  Scenario
                </th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">
                  Hits
                </th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">
                  Recovered
                </th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">
                  Rate
                </th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">
                  Avg Recovery
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {Object.entries(scenarioMap)
                .sort(([, a], [, b]) => b.hits - a.hits)
                .map(([scenario, stats]) => {
                  const rate =
                    stats.hits > 0
                      ? Math.round((stats.recovered / stats.hits) * 100)
                      : 0;
                  const avgMs =
                    stats.recovered > 0
                      ? stats.totalRecoveryMs / stats.recovered
                      : 0;
                  const avgMin = Math.round(avgMs / 60_000);

                  return (
                    <tr key={scenario} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {scenario}
                      </td>
                      <td className="px-4 py-3 text-gray-700">{stats.hits}</td>
                      <td className="px-4 py-3 text-gray-700">
                        {stats.recovered}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={
                            rate >= 80
                              ? "text-emerald-600"
                              : rate >= 50
                              ? "text-amber-600"
                              : "text-red-600"
                          }
                        >
                          {rate}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-700">
                        {avgMin > 0 ? `${avgMin}m` : "-"}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Full event timeline */}
      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          Event Timeline
        </h2>
        <ChaosTimeline events={events} />
      </section>
    </div>
  );
}

function StatBox({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-bold ${color || "text-gray-900"}`}>
        {value}
      </p>
    </div>
  );
}
