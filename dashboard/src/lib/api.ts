import useSWR from "swr";
import type { OverviewResponse, TimelineResponse, EventsResponse } from "./types";

const API = import.meta.env.VITE_API_URL || "";

async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export function useOverview() {
  return useSWR<OverviewResponse>(`${API}/api/overview`, fetcher, {
    refreshInterval: 30_000,
  });
}

export function useTimeline(date: string) {
  return useSWR<TimelineResponse>(
    date ? `${API}/api/timeline?date=${date}` : null,
    fetcher,
    { refreshInterval: 30_000 }
  );
}

export function useEvents(opts?: { pipeline?: string; from?: number; to?: number }) {
  const params = new URLSearchParams();
  if (opts?.pipeline) params.set("pipeline", opts.pipeline);
  if (opts?.from) params.set("from", String(opts.from));
  if (opts?.to) params.set("to", String(opts.to));
  return useSWR<EventsResponse>(`${API}/api/events?${params}`, fetcher, {
    refreshInterval: 30_000,
  });
}
