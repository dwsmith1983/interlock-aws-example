"""Gold ETL: Silver crypto Delta -> 2 Gold aggregation tables.

Reads all silver crypto data for the target date and produces:
1. daily_market: Latest snapshot per coin per day with market-level aggregates
2. top_movers: Top 10 gainers + top 10 losers by 24h % change per day

All outputs use Delta MERGE for idempotent re-runs.
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from delta.tables import DeltaTable
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

args = getResolvedOptions(sys.argv, ["JOB_NAME", "bucket", "table_name", "source", "tier",
                                       "par_day"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

bucket = args["bucket"]
par_day = args["par_day"].replace("-", "")

silver_path = f"s3://{bucket}/silver/crypto/"
gold_base = f"s3://{bucket}/gold/crypto"

# Read silver Delta table filtered by par_day
silver_df = spark.read.format("delta").load(silver_path) \
    .filter(F.col("par_day") == par_day)

if silver_df.rdd.isEmpty():
    print(f"No silver data for par_day={par_day}, skipping")
    job.commit()
    sys.exit(0)

record_count = silver_df.count()
print(f"Processing {record_count} silver records for par_day={par_day}")


def merge_or_create(df, path, merge_condition):
    """Write Delta table: MERGE if exists, CREATE otherwise."""
    if DeltaTable.isDeltaTable(spark, path):
        delta_table = DeltaTable.forPath(spark, path)
        delta_table.alias("target").merge(
            df.alias("source"), merge_condition
        ).whenMatchedUpdateAll() \
         .whenNotMatchedInsertAll() \
         .execute()
    else:
        df.write.format("delta").partitionBy("par_day").save(path)


# 1. Daily Market: Latest snapshot per coin per day
# Pick the latest snapshot_time per coin
latest_window = Window.partitionBy("coin_id").orderBy(F.col("snapshot_time").desc())
latest_df = silver_df.withColumn("_rank", F.row_number().over(latest_window)) \
    .filter(F.col("_rank") == 1) \
    .drop("_rank")

daily_market = latest_df.groupBy("par_day").agg(
    F.count("*").alias("coins_tracked"),
    F.sum("market_cap_usd").alias("total_market_cap_usd"),
    F.sum("volume_24h_usd").alias("total_volume_24h_usd"),
    F.avg("pct_change_24h").alias("avg_pct_change_24h"),
    F.expr("percentile_approx(pct_change_24h, 0.5)").alias("median_pct_change_24h"),
    F.avg("pct_change_1h").alias("avg_pct_change_1h"),
    F.avg("pct_change_7d").alias("avg_pct_change_7d"),
)

daily_path = f"{gold_base}/daily_market/"
merge_or_create(daily_market, daily_path, "target.par_day = source.par_day")
print(f"Wrote {daily_market.count()} daily_market records")

# 2. Top Movers: Top 10 gainers + top 10 losers by 24h % change
# Use latest snapshot per coin
gainers = latest_df.orderBy(F.col("pct_change_24h").desc()).limit(10) \
    .withColumn("mover_type", F.lit("gainer")) \
    .withColumn("mover_rank", F.row_number().over(
        Window.orderBy(F.col("pct_change_24h").desc())))

losers = latest_df.orderBy(F.col("pct_change_24h").asc()).limit(10) \
    .withColumn("mover_type", F.lit("loser")) \
    .withColumn("mover_rank", F.row_number().over(
        Window.orderBy(F.col("pct_change_24h").asc())))

top_movers = gainers.union(losers).select(
    "par_day", "coin_id", "symbol", "name", "price_usd",
    "pct_change_24h", "market_cap_usd", "volume_24h_usd",
    "mover_type", "mover_rank",
)

movers_path = f"{gold_base}/top_movers/"
merge_or_create(top_movers, movers_path,
                "target.par_day = source.par_day AND target.coin_id = source.coin_id AND target.mover_type = source.mover_type")
print(f"Wrote {top_movers.count()} top_movers records")

job.commit()
