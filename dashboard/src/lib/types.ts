export interface PipelineStatus {
  pipelineId: string;
  PK: string;
  SK: string;
  enabled: boolean;
  consecutiveFailures: number;
  lastStatus?: string;
  lastSuccessfulRun?: string;
  lastFailedRun?: string;
  lastPendingRun?: string;
  lastAlertType?: string;
  chaosActive?: boolean;
}

export interface PipelineConfig {
  PK: string;
  SK: string;
  GSI1PK: string;
  GSI1SK: string;
  config?: {
    name: string;
    archetype: string;
    traits: Record<string, unknown>;
    trigger?: Record<string, unknown>;
    sla?: {
      evalDeadlineMinutes?: number;
      completionDeadlineMinutes?: number;
    };
    schedules?: Array<{
      name: string;
      after: string;
      deadline: string;
    }>;
  };
}

export interface ChaosEvent {
  PK: string;
  SK: string;
  scenario: string;
  target: string;
  category: string;
  severity: string;
  status: string;
  injectedAt: string;
  details?: string;
  recoveredAt?: string;
  detectedAt?: string;
  recoveryTimeoutMinutes?: number;
}

export interface ChaosConfig {
  enabled: boolean;
  severity?: string;
  scenarios: Array<{
    id: string;
    category: string;
    severity: string;
    probability: number;
    cooldown_minutes: number;
    recovery_timeout_minutes: number;
    target?: string;
    description?: string;
  }>;
}

export interface Alert {
  PK: string;
  SK: string;
  alertType: string;
  severity: string;
  scheduleID?: string;
  timestamp: string;
  alertData?: Record<string, unknown>;
}

export interface JobLog {
  PK: string;
  SK: string;
  pipelineID: string;
  scheduleID: string;
  stage: string;
  status: string;
  timestamp: string;
}

export interface RunLog {
  PK: string;
  SK: string;
  timestamp?: string;
  runData?: Record<string, unknown>;
}

export interface RunHistoryEvent {
  kind: string;
  status?: string;
  timestamp: string;
  message?: string;
  traitType?: string;
  runId?: string;
  details?: Record<string, unknown>;
}

export interface RunHistory {
  pipelineId: string;
  date: string;
  scheduleId: string;
  runLog: RunLog & { runData: Record<string, unknown> };
  events: RunHistoryEvent[];
  alerts: Alert[];
  jobs: JobLog[];
}

export interface OverviewData {
  pipelines: PipelineStatus[];
  chaosEvents: ChaosEvent[];
  recentAlerts: Alert[];
  chaosConfig: ChaosConfig;
}
