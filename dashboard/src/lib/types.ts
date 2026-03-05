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

export interface TimelineResponse {
  date: string;
  pipelines: Record<string, Record<string, PipelineEvent[]>>;
}

export interface EventsResponse {
  events: PipelineEvent[];
}
