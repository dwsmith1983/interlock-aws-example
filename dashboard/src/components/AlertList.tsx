"use client";

import type { Alert } from "@/lib/types";
import { SeverityBadge } from "./StatusBadge";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function AlertList({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-500">No recent alerts</p>
    );
  }

  return (
    <div className="divide-y divide-gray-100">
      {alerts.map((alert, i) => (
        <div key={alert.SK || i} className="flex items-center justify-between py-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <SeverityBadge severity={alert.severity} />
              <span className="text-sm font-medium text-gray-900">
                {alert.alertType}
              </span>
            </div>
            <p className="mt-0.5 truncate text-xs text-gray-500">
              {alert.PK?.replace("PIPELINE#", "")}
              {alert.scheduleID ? ` / ${alert.scheduleID}` : ""}
            </p>
          </div>
          <span className="ml-4 shrink-0 text-xs text-gray-400">
            {formatTime(alert.timestamp)}
          </span>
        </div>
      ))}
    </div>
  );
}
