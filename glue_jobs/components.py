"""DataFlow components for bronze → silver aggregation Glue jobs."""

from __future__ import annotations

from typing import Any

from pyspark.sql import functions as F

from pyspark_pipeline_framework.runtime.dataflow import DataFlow


class ReadBronzeDelta(DataFlow):
    """Read a Delta table from bronze/{stream}/ filtered by partition keys."""

    def __init__(self, s3_bucket: str, stream: str, par_day: str, par_hour: str | None = None) -> None:
        super().__init__()
        self._s3_bucket = s3_bucket
        self._stream = stream
        self._par_day = par_day
        self._par_hour = par_hour
        self._output_view = f"bronze_{stream}"

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ReadBronzeDelta:
        return cls(
            s3_bucket=config["s3_bucket"],
            stream=config["stream"],
            par_day=config["par_day"],
            par_hour=config.get("par_hour"),
        )

    @property
    def name(self) -> str:
        return f"ReadBronzeDelta({self._stream})"

    def run(self) -> None:
        path = f"s3://{self._s3_bucket}/bronze/{self._stream}"
        df = self.spark.read.format("delta").load(path)

        df = df.filter(F.col("par_day") == self._par_day)
        if self._par_hour is not None:
            df = df.filter(F.col("par_hour") == self._par_hour)

        df.createOrReplaceTempView(self._output_view)
        self.logger.info(
            "Loaded %s (par_day=%s, par_hour=%s) into view '%s'",
            self._stream, self._par_day, self._par_hour, self._output_view,
        )


class CdrAggTransform(DataFlow):
    """Aggregate CDR records by phone_hash_out."""

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> CdrAggTransform:
        return cls()

    @property
    def name(self) -> str:
        return "CdrAggTransform"

    def run(self) -> None:
        df = self.spark.table("bronze_cdr")

        agg = df.groupBy("phone_hash_out").agg(
            F.count("*").alias("total_calls"),
            F.sum(F.lit(10.0)).alias("total_duration_s"),  # each ping = 10s interval
            F.countDistinct("phone_hash_in").alias("unique_contacts"),
            F.collect_set("cell_tower").alias("unique_towers"),
        )
        agg = agg.withColumn(
            "avg_call_duration_s",
            F.col("total_duration_s") / F.col("total_calls"),
        )

        agg.createOrReplaceTempView("cdr_agg")
        self.logger.info("CDR aggregation complete")


class SeqAggTransform(DataFlow):
    """Aggregate SEQ records by phone_hash + host_name."""

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SeqAggTransform:
        return cls()

    @property
    def name(self) -> str:
        return "SeqAggTransform"

    def run(self) -> None:
        df = self.spark.table("bronze_seq")

        agg = df.groupBy("phone_hash", "host_name").agg(
            F.first("site_name").alias("site_name"),
            F.count("*").alias("total_pings"),
            F.collect_set("cell_tower").alias("unique_towers"),
            F.sum(F.lit(10.0)).alias("total_session_duration_s"),  # each ping = 10s
        )

        agg.createOrReplaceTempView("seq_agg")
        self.logger.info("SEQ aggregation complete")


class WriteSilverDelta(DataFlow):
    """Write aggregated data as Delta Lake to silver/{table}/."""

    def __init__(
        self,
        s3_bucket: str,
        output_table: str,
        input_view: str,
        par_day: str,
        par_hour: str | None = None,
    ) -> None:
        super().__init__()
        self._s3_bucket = s3_bucket
        self._output_table = output_table
        self._input_view = input_view
        self._par_day = par_day
        self._par_hour = par_hour

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> WriteSilverDelta:
        return cls(
            s3_bucket=config["s3_bucket"],
            output_table=config["output_table"],
            input_view=config["input_view"],
            par_day=config["par_day"],
            par_hour=config.get("par_hour"),
        )

    @property
    def name(self) -> str:
        return f"WriteSilverDelta({self._output_table})"

    def run(self) -> None:
        df = self.spark.table(self._input_view)

        # Add partition columns
        df = df.withColumn("par_day", F.lit(self._par_day))
        if self._par_hour is not None:
            df = df.withColumn("par_hour", F.lit(self._par_hour))

        path = f"s3://{self._s3_bucket}/silver/{self._output_table}"
        partition_cols = ["par_day"]
        if self._par_hour is not None:
            partition_cols.append("par_hour")

        df.write.format("delta").mode("append").partitionBy(*partition_cols).save(path)
        self.logger.info(
            "Wrote silver/%s (par_day=%s, par_hour=%s)",
            self._output_table, self._par_day, self._par_hour,
        )
