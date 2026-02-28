"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";
import { usePipelineHistory } from "@/lib/api";
import { RunHistoryTimeline } from "@/components/RunHistoryTimeline";

function HistoryContent({ id }: { id: string }) {
  const searchParams = useSearchParams();
  const date = searchParams.get("date") || "";
  const schedule = searchParams.get("schedule") || "";

  const { data, isLoading, error } = usePipelineHistory(id, date, schedule);

  if (!date || !schedule) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
        Missing required query parameters: <code>date</code> and{" "}
        <code>schedule</code>.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500">
        <Link href="/" className="hover:text-gray-700">
          Dashboard
        </Link>
        <span className="mx-2">/</span>
        <Link href={`/pipeline/${id}`} className="hover:text-gray-700">
          {id}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900">Run History</span>
      </nav>

      {isLoading && (
        <div className="space-y-4">
          <div className="h-32 animate-pulse rounded-lg bg-gray-200" />
          <div className="h-64 animate-pulse rounded-lg bg-gray-200" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
          Failed to load run history. Please try again.
        </div>
      )}

      {data && <RunHistoryTimeline data={data} />}
    </div>
  );
}

export function HistoryPageContent({ id }: { id: string }) {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <div className="h-8 w-64 animate-pulse rounded bg-gray-200" />
          <div className="h-32 animate-pulse rounded-lg bg-gray-200" />
        </div>
      }
    >
      <HistoryContent id={id} />
    </Suspense>
  );
}
