export interface PipelineEvent {
  eventType: string;
  timestamp: number;
  pipelineId: string;
  scheduleId?: string;
  date?: string;
  message: string;
}

export interface PipelineSummary {
  events: number;
  lastEvent: {
    eventType: string;
    timestamp: number;
    message: string;
  } | null;
  types: Record<string, number>;
  recentCounts?: number[];
}

export interface OverviewResponse {
  pipelines: Record<string, PipelineSummary>;
}

export interface PipelineEventsResponse {
  events: PipelineEvent[];
  pipeline: string;
  date: string;
  hour: string | null;
}

export interface EventsResponse {
  events: PipelineEvent[];
}

export interface MetricsResponse {
  byType: Record<string, number>;
  byPipeline: Record<string, number>;
  byHour: Record<string, number>;
  sla: { SLA_MET: number; SLA_WARNING: number; SLA_BREACH: number };
  totalEvents: number;
}
