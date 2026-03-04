"use client";

import Link from "next/link";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import StatusBadge from "./StatusBadge";
import type { PipelineSummary } from "@/lib/types";
import { eventColor } from "@/lib/events";

function timeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

interface Props {
  name: string;
  summary: PipelineSummary;
}

export default function PipelineCard({ name, summary }: Props) {
  const lastType = summary.lastEvent?.eventType;
  const color = lastType ? eventColor(lastType) : "#94a3b8";
  const sparkData = (summary.recentCounts ?? []).map((v, i) => ({ i, v }));

  return (
    <Link href={`/pipelines?pipeline=${name}`}>
      <div className="glass p-4 hover:bg-white/[0.08] transition-colors cursor-pointer">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
            <h3 className="text-sm font-semibold text-white">{name}</h3>
          </div>
          <span className="text-xs text-slate-500">
            {summary.events} event{summary.events !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Sparkline */}
        {sparkData.length > 0 && (
          <div className="mt-3 h-10">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparkData}>
                <Line
                  type="monotone"
                  dataKey="v"
                  stroke={color}
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {summary.lastEvent ? (
          <div className="mt-3 flex items-center gap-2">
            <StatusBadge type={summary.lastEvent.eventType} />
            <span className="text-xs text-slate-500">{timeAgo(summary.lastEvent.timestamp)}</span>
          </div>
        ) : (
          <p className="mt-3 text-xs text-slate-500">No recent events</p>
        )}
      </div>
    </Link>
  );
}
