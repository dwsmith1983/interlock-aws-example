"use client";

import { useState } from "react";
import { usePipelineEvents } from "@/lib/api";
import HourGrid from "@/components/HourGrid";
import EventTimeline from "@/components/EventTimeline";

const PIPELINE_GROUPS: Record<string, string[]> = {
  CDR: ["bronze-cdr", "silver-cdr-hour", "silver-cdr-day"],
  SEQ: ["bronze-seq", "silver-seq-hour", "silver-seq-day"],
};

const ALL_PIPELINES = Object.values(PIPELINE_GROUPS).flat();
const GROUP_NAMES = Object.keys(PIPELINE_GROUPS);

function todayUTC(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function PipelinesPage() {
  const [selectedGroup, setSelectedGroup] = useState<string | undefined>(undefined);
  const [selectedPipeline, setSelectedPipeline] = useState(ALL_PIPELINES[0]);
  const [selectedDate, setSelectedDate] = useState(todayUTC);
  const [selectedHour, setSelectedHour] = useState<string | undefined>(undefined);

  const visiblePipelines = selectedGroup
    ? PIPELINE_GROUPS[selectedGroup]
    : ALL_PIPELINES;

  // When switching groups, reset pipeline to first in group if current is not visible
  function handleGroupChange(group: string | undefined) {
    setSelectedGroup(group);
    const pipelines = group ? PIPELINE_GROUPS[group] : ALL_PIPELINES;
    if (!pipelines.includes(selectedPipeline)) {
      setSelectedPipeline(pipelines[0]);
    }
    setSelectedHour(undefined);
  }

  // Fetch events for the full day (no hour filter) so HourGrid can show all hours
  const { data: dayData, isLoading: dayLoading, error: dayError } = usePipelineEvents(
    selectedPipeline,
    selectedDate,
  );

  // Fetch filtered events when an hour is selected
  const { data: hourData, isLoading: hourLoading, error: hourError } = usePipelineEvents(
    selectedHour ? selectedPipeline : "",
    selectedDate,
    selectedHour,
  );

  const dayEvents = dayData?.events ?? [];
  const displayEvents = selectedHour ? (hourData?.events ?? []) : dayEvents;
  const isLoading = dayLoading || (selectedHour ? hourLoading : false);
  const error = dayError || (selectedHour ? hourError : null);

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">Pipeline Detail</h1>
      <p className="mt-1 text-sm text-gray-600">
        Select a pipeline, date, and optionally drill into a specific hour.
      </p>

      {/* Controls */}
      <div className="mt-6 flex flex-wrap items-end gap-4">
        {/* Group tabs */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Group</label>
          <div className="flex gap-1">
            <button
              onClick={() => handleGroupChange(undefined)}
              className={`px-3 py-1.5 text-sm font-medium rounded ${
                selectedGroup === undefined
                  ? "bg-gray-900 text-white"
                  : "bg-gray-200 text-gray-700 hover:bg-gray-300"
              }`}
            >
              All
            </button>
            {GROUP_NAMES.map((g) => (
              <button
                key={g}
                onClick={() => handleGroupChange(g)}
                className={`px-3 py-1.5 text-sm font-medium rounded ${
                  selectedGroup === g
                    ? "bg-gray-900 text-white"
                    : "bg-gray-200 text-gray-700 hover:bg-gray-300"
                }`}
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        {/* Pipeline select */}
        <div>
          <label htmlFor="pipeline-select" className="block text-xs font-medium text-gray-500 mb-1">
            Pipeline
          </label>
          <select
            id="pipeline-select"
            value={selectedPipeline}
            onChange={(e) => {
              setSelectedPipeline(e.target.value);
              setSelectedHour(undefined);
            }}
            className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          >
            {visiblePipelines.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        {/* Date picker */}
        <div>
          <label htmlFor="date-picker" className="block text-xs font-medium text-gray-500 mb-1">
            Date (UTC)
          </label>
          <input
            id="date-picker"
            type="date"
            value={selectedDate}
            onChange={(e) => {
              setSelectedDate(e.target.value);
              setSelectedHour(undefined);
            }}
            className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          />
        </div>
      </div>

      {/* Hour Grid */}
      <section className="mt-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-3">
          Hourly Distribution
          {selectedHour !== undefined && (
            <span className="ml-2 text-sm font-normal text-gray-500">
              (showing hour {selectedHour})
            </span>
          )}
        </h2>
        {dayLoading ? (
          <p className="text-sm text-gray-500">Loading hours...</p>
        ) : dayError ? (
          <p className="text-sm text-red-600">{dayError.message}</p>
        ) : (
          <HourGrid
            events={dayEvents}
            selectedHour={selectedHour}
            onSelectHour={setSelectedHour}
          />
        )}
      </section>

      {/* Event Timeline */}
      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-700 mb-3">
          Events
          <span className="ml-2 text-sm font-normal text-gray-500">
            ({displayEvents.length} event{displayEvents.length !== 1 ? "s" : ""})
          </span>
        </h2>
        {isLoading ? (
          <p className="text-sm text-gray-500">Loading events...</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error.message}</p>
        ) : (
          <EventTimeline events={displayEvents} />
        )}
      </section>
    </div>
  );
}
