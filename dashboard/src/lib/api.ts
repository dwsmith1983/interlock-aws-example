import useSWR from "swr";
import type {
  OverviewData,
  PipelineConfig,
  PipelineStatus,
  JobLog,
  RunLog,
  RunHistory,
  ChaosEvent,
  ChaosConfig,
  Alert,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001/dashboard";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const SWR_OPTIONS = {
  refreshInterval: 30_000, // 30s polling
  revalidateOnFocus: true,
};

export function useOverview() {
  return useSWR<OverviewData>(`${API_BASE}/overview`, fetcher, SWR_OPTIONS);
}

export function usePipelines() {
  return useSWR<{ pipelines: PipelineConfig[] }>(
    `${API_BASE}/pipelines`,
    fetcher,
    SWR_OPTIONS
  );
}

export function usePipelineStatus(id: string) {
  return useSWR<PipelineStatus>(
    `${API_BASE}/pipelines/${id}/status`,
    fetcher,
    SWR_OPTIONS
  );
}

export function usePipelineJobs(id: string) {
  return useSWR<{ pipelineId: string; jobs: JobLog[] }>(
    `${API_BASE}/pipelines/${id}/jobs`,
    fetcher,
    SWR_OPTIONS
  );
}

export function usePipelineRunlogs(id: string) {
  return useSWR<{ pipelineId: string; runlogs: RunLog[] }>(
    `${API_BASE}/pipelines/${id}/runlogs`,
    fetcher,
    SWR_OPTIONS
  );
}

export function usePipelineHistory(id: string, date: string, scheduleId: string) {
  const key =
    date && scheduleId
      ? `${API_BASE}/pipelines/${id}/history?date=${date}&schedule=${scheduleId}`
      : null;
  return useSWR<RunHistory>(key, fetcher, SWR_OPTIONS);
}

export function useChaosEvents() {
  return useSWR<{ events: ChaosEvent[] }>(
    `${API_BASE}/chaos/events`,
    fetcher,
    SWR_OPTIONS
  );
}

export function useChaosConfig() {
  return useSWR<ChaosConfig>(
    `${API_BASE}/chaos/config`,
    fetcher,
    SWR_OPTIONS
  );
}

export function useAlerts() {
  return useSWR<{ alerts: Alert[] }>(
    `${API_BASE}/alerts`,
    fetcher,
    SWR_OPTIONS
  );
}
