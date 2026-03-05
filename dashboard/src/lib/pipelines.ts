export const ALL_PIPELINES = [
  "bronze-cdr",
  "bronze-seq",
  "silver-cdr-hour",
  "silver-seq-hour",
  "silver-cdr-day",
  "silver-seq-day",
] as const;

export type PipelineId = (typeof ALL_PIPELINES)[number];
