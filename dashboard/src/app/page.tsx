"use client";

import { useOverview } from "@/lib/api";
import PipelineCard from "@/components/PipelineCard";

const CDR_PIPELINES = ["bronze-cdr", "silver-cdr-hour", "silver-cdr-day"];
const SEQ_PIPELINES = ["bronze-seq", "silver-seq-hour", "silver-seq-day"];

export default function OverviewPage() {
  const { data, error, isLoading } = useOverview();

  if (isLoading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pipeline Overview</h1>
        <p className="mt-2 text-gray-600">Loading pipeline data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pipeline Overview</h1>
        <p className="mt-2 text-red-600">{error.message}</p>
      </div>
    );
  }

  const pipelines = data?.pipelines ?? {};

  if (Object.keys(pipelines).length === 0) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pipeline Overview</h1>
        <p className="mt-2 text-gray-600">No events in the last 24 hours</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">Pipeline Overview</h1>

      <section className="mt-6">
        <h2 className="text-lg font-semibold text-gray-700">CDR Pipelines</h2>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {CDR_PIPELINES.map((id) => {
            const summary = pipelines[id];
            if (!summary) return null;
            return <PipelineCard key={id} name={id} summary={summary} />;
          })}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-700">SEQ Pipelines</h2>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {SEQ_PIPELINES.map((id) => {
            const summary = pipelines[id];
            if (!summary) return null;
            return <PipelineCard key={id} name={id} summary={summary} />;
          })}
        </div>
      </section>
    </div>
  );
}
