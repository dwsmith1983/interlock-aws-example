"use client";

import { useAlerts } from "@/lib/api";
import { SeverityBadge } from "@/components/StatusBadge";

export default function AlertsPage() {
  const { data, isLoading } = useAlerts();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-200" />
        <div className="grid gap-4 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-gray-200" />
          ))}
        </div>
        <div className="h-96 animate-pulse rounded-lg bg-gray-200" />
      </div>
    );
  }

  const alerts = data?.alerts || [];

  const bySeverity: Record<string, number> = {};
  const byType: Record<string, number> = {};
  for (const a of alerts) {
    bySeverity[a.severity] = (bySeverity[a.severity] || 0) + 1;
    byType[a.alertType] = (byType[a.alertType] || 0) + 1;
  }

  const pipelineFromPK = (pk: string) => pk.replace("PIPELINE#", "").replace("ALERT#", "");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Alerts</h1>
        <p className="mt-1 text-sm text-gray-500">
          Pipeline alerts, SLA breaches, and evaluation failures
        </p>
      </div>

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-4">
        <StatBox label="Total Alerts" value={alerts.length} />
        <StatBox
          label="Critical"
          value={bySeverity["critical"] || 0}
          color="text-red-600"
        />
        <StatBox
          label="Error"
          value={bySeverity["error"] || 0}
          color="text-orange-600"
        />
        <StatBox
          label="Warning"
          value={bySeverity["warning"] || 0}
          color="text-amber-600"
        />
      </div>

      {/* Alert type breakdown */}
      {Object.keys(byType).length > 0 && (
        <section className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">
            By Type
          </h2>
          <div className="flex flex-wrap gap-3">
            {Object.entries(byType)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <span
                  key={type}
                  className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-sm"
                >
                  <span className="font-medium text-gray-900">{type}</span>
                  <span className="text-gray-500">{count}</span>
                </span>
              ))}
          </div>
        </section>
      )}

      {/* Alert table */}
      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          Recent Alerts ({alerts.length})
        </h2>
        {alerts.length === 0 ? (
          <p className="text-sm text-gray-500">No alerts recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Time</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Severity</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Type</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Pipeline</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Schedule</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {alerts.map((alert, i) => (
                  <tr key={`${alert.PK}-${alert.SK}-${i}`} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                      {formatTime(alert.timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={alert.severity} />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {alert.alertType}
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      {pipelineFromPK(alert.PK)}
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      {alert.scheduleID || "-"}
                    </td>
                    <td className="px-4 py-3 text-gray-500 max-w-xs truncate">
                      {alert.alertData ? JSON.stringify(alert.alertData) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
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
