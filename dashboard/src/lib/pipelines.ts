export const CDR_PIPELINES = ["bronze-cdr", "silver-cdr-hour", "silver-cdr-day"];
export const SEQ_PIPELINES = ["bronze-seq", "silver-seq-hour", "silver-seq-day"];
export const ALL_PIPELINES = [...CDR_PIPELINES, ...SEQ_PIPELINES];
