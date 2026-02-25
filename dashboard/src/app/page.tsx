"use client";

import { useOverview } from "@/lib/api";
import { PipelineCard } from "@/components/PipelineCard";
import { AlertList } from "@/components/AlertList";
import { ChaosTimeline } from "@/components/ChaosTimeline";
import { StatusBadge } from "@/components/StatusBadge";

export default function OverviewPage() {
  const { data, error, isLoading } = useOverview();

  if (isLoading) return <LoadingSkeleton />;
  if (error) return <ErrorState message="Failed to load dashboard data" />;
  if (!data) return null;

  const chaosEnabled = data.chaosConfig?.enabled ?? false;
  const recoveredCount = data.chaosEvents.filter(
    (e) => e.status === "RECOVERED"
  ).length;
  const totalChaos = data.chaosEvents.length;
  const recoveryRate =
    totalChaos > 0 ? Math.round((recoveredCount / totalChaos) * 100) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Pipeline Dashboard
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Real-time health monitoring for the medallion pipeline
        </p>
      </div>

      {/* Chaos banner */}
      <div
        className={`rounded-lg border p-4 ${
          chaosEnabled
            ? "border-orange-200 bg-orange-50"
            : "border-gray-200 bg-gray-50"
        }`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <svg
              className={`h-5 w-5 ${
                chaosEnabled ? "text-orange-500" : "text-gray-400"
              }`}
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
            <span className="font-medium text-gray-900">
              Chaos Testing:{" "}
              <StatusBadge status={chaosEnabled ? "INJECTED" : "disabled"} />
            </span>
          </div>
          <div className="flex gap-6 text-sm text-gray-600">
            <span>
              Events: <strong>{totalChaos}</strong>
            </span>
            <span>
              Recovery rate: <strong>{recoveryRate}%</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Pipeline cards */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-gray-800">Pipelines</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {data.pipelines.map((p) => (
            <PipelineCard key={p.pipelineId} pipeline={p} />
          ))}
        </div>
      </section>

      {/* Two-column: alerts + chaos */}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-3 text-lg font-semibold text-gray-800">
            Recent Alerts
          </h2>
          <AlertList alerts={data.recentAlerts.slice(0, 10)} />
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-3 text-lg font-semibold text-gray-800">
            Recent Chaos Events
          </h2>
          <ChaosTimeline events={data.chaosEvents.slice(0, 8)} />
        </section>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-8 w-64 animate-pulse rounded bg-gray-200" />
      <div className="h-16 animate-pulse rounded-lg bg-gray-200" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-36 animate-pulse rounded-lg bg-gray-200" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-64 animate-pulse rounded-lg bg-gray-200" />
        <div className="h-64 animate-pulse rounded-lg bg-gray-200" />
      </div>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="text-center">
        <svg
          className="mx-auto h-12 w-12 text-red-400"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
          />
        </svg>
        <p className="mt-2 text-sm text-gray-600">{message}</p>
        <p className="mt-1 text-xs text-gray-400">
          Check that the API is running and NEXT_PUBLIC_API_URL is set
        </p>
      </div>
    </div>
  );
}
