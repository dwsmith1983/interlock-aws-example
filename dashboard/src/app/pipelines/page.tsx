"use client";

import { Suspense, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { useEvents } from "@/lib/api";
import Heatmap from "@/components/Heatmap";
import EventTimeline from "@/components/EventTimeline";
import { ALL_PIPELINES, CDR_PIPELINES, SEQ_PIPELINES } from "@/lib/pipelines";

type Group = "all" | "cdr" | "seq";

function todayUTC(): string {
  return new Date().toISOString().slice(0, 10);
}

function PipelinesInner() {
  const searchParams = useSearchParams();
  const initialPipeline = searchParams.get("pipeline") || "";

  const [group, setGroup] = useState<Group>("all");
  const [selectedPipeline, setSelectedPipeline] = useState(initialPipeline);
  const [selectedHour, setSelectedHour] = useState<string>("");
  const [date, setDate] = useState(todayUTC);

  const visiblePipelines = group === "cdr" ? CDR_PIPELINES : group === "seq" ? SEQ_PIPELINES : ALL_PIPELINES;

  // Load events for the selected date (full day UTC)
  const dayStart = new Date(date + "T00:00:00Z").getTime();
  const dayEnd = dayStart + 86400000;
  const { data } = useEvents(undefined, dayStart, dayEnd);
  const events = data?.events ?? [];

  // Filter events for the heatmap based on visible pipelines
  const heatmapEvents = useMemo(() => {
    const visible = new Set(visiblePipelines);
    return events.filter((e) => visible.has(e.pipelineId));
  }, [events, visiblePipelines]);

  // Filter events for the timeline based on selected cell
  const timelineEvents = useMemo(() => {
    if (!selectedPipeline || !selectedHour) return [];
    return events.filter((e) => {
      if (e.pipelineId !== selectedPipeline) return false;
      const hour = String(new Date(e.timestamp).getUTCHours()).padStart(2, "0");
      return hour === selectedHour;
    });
  }, [events, selectedPipeline, selectedHour]);

  const handleSelectCell = (p: string, h: string) => {
    setSelectedPipeline(p);
    setSelectedHour(h);
  };

  const GROUPS: { key: Group; label: string }[] = [
    { key: "all", label: "All" },
    { key: "cdr", label: "CDR" },
    { key: "seq", label: "SEQ" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-white">Pipelines</h1>

      {/* Filters */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {GROUPS.map((g) => (
            <button
              key={g.key}
              onClick={() => setGroup(g.key)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                group === g.key
                  ? "bg-white/10 text-white border border-white/20"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {g.label}
            </button>
          ))}
        </div>

        <select
          value={selectedPipeline}
          onChange={(e) => { setSelectedPipeline(e.target.value); setSelectedHour(""); }}
          aria-label="Filter by pipeline"
          className="glass-subtle px-3 py-1.5 text-xs text-slate-300 bg-transparent outline-none cursor-pointer"
        >
          <option value="" className="bg-[#0a1628]">All pipelines</option>
          {visiblePipelines.map((p) => (
            <option key={p} value={p} className="bg-[#0a1628]">{p}</option>
          ))}
        </select>

        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          aria-label="Select date"
          className="glass-subtle px-3 py-1.5 text-xs text-slate-300 bg-transparent outline-none cursor-pointer"
        />
      </div>

      {/* Two-panel layout */}
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Heatmap */}
        <div className="lg:col-span-3 glass p-4">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Activity Heatmap</h2>
          <Heatmap
            events={heatmapEvents}
            pipelines={visiblePipelines}
            selectedHour={selectedHour}
            selectedPipeline={selectedPipeline}
            onSelectCell={handleSelectCell}
          />
        </div>

        {/* Event Timeline */}
        <div className="lg:col-span-2 glass p-4 max-h-[500px] overflow-y-auto">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Event Timeline
            {selectedPipeline && selectedHour && (
              <span className="text-slate-500 font-normal ml-2">
                {selectedPipeline} T{selectedHour}
              </span>
            )}
          </h2>
          <EventTimeline events={timelineEvents} />
        </div>
      </div>
    </div>
  );
}

export default function PipelinesPage() {
  return (
    <Suspense>
      <PipelinesInner />
    </Suspense>
  );
}
