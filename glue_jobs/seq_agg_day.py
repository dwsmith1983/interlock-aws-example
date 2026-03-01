"""Glue job: daily SEQ aggregation (bronze/seq → silver/seq_agg_day)."""

from pyspark_pipeline_framework.core.config import (
    ComponentConfig,
    ComponentType,
    PipelineConfig,
    PipelineMode,
    SparkConfig,
)
from pyspark_pipeline_framework.runner import LoggingHooks, SimplePipelineRunner

from glue_jobs.args import resolve_args


def main() -> None:
    args = resolve_args(["s3_bucket"], ["par_day"])

    config = PipelineConfig(
        name="seq-agg-day",
        version="1.0.0",
        spark=SparkConfig(app_name="seq-agg-day"),
        components=[
            ComponentConfig(
                name="read_bronze",
                component_type=ComponentType.SOURCE,
                class_path="glue_jobs.components.ReadBronzeDelta",
                config={"s3_bucket": args["s3_bucket"], "stream": "seq", "par_day": args["par_day"]},
            ),
            ComponentConfig(
                name="aggregate",
                component_type=ComponentType.TRANSFORMATION,
                class_path="glue_jobs.components.SeqAggTransform",
                depends_on=["read_bronze"],
                config={},
            ),
            ComponentConfig(
                name="write_silver",
                component_type=ComponentType.SINK,
                class_path="glue_jobs.components.WriteSilverDelta",
                depends_on=["aggregate"],
                config={
                    "s3_bucket": args["s3_bucket"],
                    "output_table": "seq_agg_day",
                    "input_view": "seq_agg",
                    "par_day": args["par_day"],
                },
            ),
        ],
        mode=PipelineMode.BATCH,
    )

    runner = SimplePipelineRunner(config, hooks=LoggingHooks())
    result = runner.run()
    print(f"Pipeline {config.name}: {result.status} ({result.total_duration_ms}ms)")


if __name__ == "__main__":
    main()
