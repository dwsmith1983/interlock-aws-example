import { useState } from "react";
import { format } from "date-fns";
import { useOverview, useTimeline, useEvents } from "@/lib/api";
import { ALL_PIPELINES } from "@/lib/pipelines";
import { FAILURE_TYPES, WARNING_TYPES } from "@/lib/events";
import PipelineCard from "@/components/PipelineCard";
import PipelineDetail from "@/components/PipelineDetail";
import TimelineSwimlane from "@/components/TimelineSwimlane";
import EventRow from "@/components/EventRow";

type EventFilter = "all" | "failures" | "sla";

export default function App() {
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [eventFilter, setEventFilter] = useState<EventFilter>("all");

  const { data: overview, isLoading: overviewLoading } = useOverview();
  const { data: timeline } = useTimeline(selectedDate);
  const now = Date.now();
  const { data: eventsData } = useEvents({ from: now - 86400000, to: now });

  const nowHour = new Date().getUTCHours();

  const allEvents = (eventsData?.events ?? [])
    .sort((a, b) => b.timestamp - a.timestamp)
    .filter((e) => {
      if (eventFilter === "failures") return FAILURE_TYPES.has(e.eventType);
      if (eventFilter === "sla")
        return e.eventType.startsWith("SLA_") || WARNING_TYPES.has(e.eventType);
      return true;
    })
    .slice(0, 50);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="h-12 border-b border-border bg-surface sticky top-0 z-10 flex items-center justify-between px-6">
        <span className="font-semibold text-base text-text tracking-tight">Interlock</span>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <span className="text-xs text-text-muted">
            Live &mdash; {format(new Date(), "HH:mm:ss")}
          </span>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-5 space-y-5">
        {/* Section 1: Pipeline Status Cards */}
        <section>
          <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
            Pipeline Status
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {ALL_PIPELINES.map((id) => (
              <PipelineCard
                key={id}
                id={id}
                summary={overview?.pipelines[id]}
                selected={selectedPipeline === id}
                onClick={() =>
                  setSelectedPipeline(selectedPipeline === id ? null : id)
                }
              />
            ))}
          </div>

          {selectedPipeline && (
            <div className="mt-3">
              <PipelineDetail
                id={selectedPipeline}
                summary={overview?.pipelines[selectedPipeline]}
                onClose={() => setSelectedPipeline(null)}
              />
            </div>
          )}
        </section>

        {/* Section 2: Timeline Swimlanes */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wide">
              24-Hour Timeline
            </h2>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="text-xs border border-border rounded px-2 py-1 bg-surface text-text"
            />
          </div>
          <div className="border border-border rounded-lg bg-surface p-4 space-y-1.5">
            {ALL_PIPELINES.map((id) => (
              <TimelineSwimlane
                key={id}
                id={id}
                hours={timeline?.pipelines[id] ?? {}}
                nowHour={nowHour}
              />
            ))}
            {/* Hour labels */}
            <div className="flex items-center gap-2">
              <span className="w-28 shrink-0" />
              <div className="grid grid-cols-24 gap-px flex-1">
                {Array.from({ length: 24 }, (_, h) => (
                  <span key={h} className="text-center text-[10px] text-text-muted">
                    {h % 6 === 0 ? String(h).padStart(2, "0") : ""}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Section 3: Events Feed */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wide">
              Recent Events
            </h2>
            <div className="flex gap-1">
              {(["all", "failures", "sla"] as EventFilter[]).map((f) => (
                <button
                  key={f}
                  onClick={() => setEventFilter(f)}
                  className={`px-3 py-1 text-xs rounded-full border transition-all ${
                    eventFilter === f
                      ? "bg-accent text-white border-accent"
                      : "border-border text-text-muted hover:border-accent/40"
                  }`}
                >
                  {f === "all" ? "All" : f === "failures" ? "Failures" : "SLA"}
                </button>
              ))}
            </div>
          </div>
          <div className="border border-border rounded-lg bg-surface max-h-96 overflow-y-auto">
            {overviewLoading ? (
              <p className="p-4 text-xs text-text-muted">Loading events...</p>
            ) : allEvents.length === 0 ? (
              <p className="p-4 text-xs text-text-muted">No events match filter.</p>
            ) : (
              allEvents.map((e, i) => (
                <EventRow key={`${e.timestamp}-${i}`} event={e} />
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
