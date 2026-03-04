import useSWR from "swr";
import type {
  OverviewResponse,
  PipelineEventsResponse,
  EventsResponse,
  MetricsResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function useOverview() {
  return useSWR<OverviewResponse>(
    `${API_BASE}/api/overview`,
    fetcher,
    { refreshInterval: 30000 }
  );
}

export function usePipelineEvents(pipelineId: string, date: string, hour?: string) {
  const params = new URLSearchParams({ date });
  if (hour) params.set("hour", hour);
  return useSWR<PipelineEventsResponse>(
    pipelineId && date
      ? `${API_BASE}/api/pipelines/${pipelineId}/events?${params}`
      : null,
    fetcher,
    { refreshInterval: 30000 }
  );
}

export function useEvents(type?: string, from?: number, to?: number) {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (from) params.set("from", String(from));
  if (to) params.set("to", String(to));
  return useSWR<EventsResponse>(
    `${API_BASE}/api/events?${params}`,
    fetcher,
    { refreshInterval: 30000 }
  );
}

export function useMetrics(from?: number, to?: number) {
  const params = new URLSearchParams();
  if (from) params.set("from", String(from));
  if (to) params.set("to", String(to));
  return useSWR<MetricsResponse>(
    `${API_BASE}/api/metrics?${params}`,
    fetcher,
    { refreshInterval: 30000 }
  );
}
