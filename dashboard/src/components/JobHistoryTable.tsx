"use client";

import type { JobLog } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function JobHistoryTable({ jobs }: { jobs: JobLog[] }) {
  if (jobs.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-500">
        No job history yet
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Time
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Schedule
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Stage
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {jobs.map((job, i) => (
            <tr key={job.SK || i} className="hover:bg-gray-50">
              <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                {formatTime(job.timestamp)}
              </td>
              <td className="px-4 py-3 font-mono text-xs text-gray-700">
                {job.scheduleID}
              </td>
              <td className="px-4 py-3 text-gray-700">{job.stage || "-"}</td>
              <td className="px-4 py-3">
                <StatusBadge status={job.status?.toUpperCase() || "UNKNOWN"} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
