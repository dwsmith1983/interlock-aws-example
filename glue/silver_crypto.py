"""Silver ETL: Bronze crypto JSONL -> Silver Delta table.

Reads bronze JSONL files for the target par_day/par_hour, casts string numerics
to doubles, deduplicates by coin_id+snapshot_time, validates records, quarantines
bad data, and upserts good data into the silver Delta table via MERGE.
"""

import json
import sys
import time
from datetime import datetime, timezone

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from delta.tables import DeltaTable
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
)
from pyspark.sql.window import Window

args = getResolvedOptions(sys.argv, ["JOB_NAME", "bucket", "table_name", "source", "tier",
                                       "par_day", "par_hour"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

bucket = args["bucket"]
source = args["source"]
table_name = args["table_name"]
par_day = args["par_day"].replace("-", "")
par_hour = args["par_hour"]
pipeline_id = "crypto-silver"

bronze_path = f"s3://{bucket}/bronze/{source}/par_day={par_day}/par_hour={par_hour}/"
silver_path = f"s3://{bucket}/silver/{source}/"
quarantine_path = f"s3://{bucket}/quarantine/{source}/"

# Read bronze JSONL — all fields come as strings from CoinLore API
df = spark.read.json(bronze_path)

if df.rdd.isEmpty():
    print(f"No data found at {bronze_path}, skipping")
    job.commit()
    sys.exit(0)

# Cast string numerics to proper types
df = df.withColumn("coin_id", F.col("coin_id").cast(StringType())) \
       .withColumn("symbol", F.col("symbol").cast(StringType())) \
       .withColumn("name", F.col("name").cast(StringType())) \
       .withColumn("name_slug", F.col("name_slug").cast(StringType())) \
       .withColumn("market_rank", F.col("market_rank").cast(IntegerType())) \
       .withColumn("price_usd", F.col("price_usd").cast(DoubleType())) \
       .withColumn("pct_change_1h", F.col("pct_change_1h").cast(DoubleType())) \
       .withColumn("pct_change_24h", F.col("pct_change_24h").cast(DoubleType())) \
       .withColumn("pct_change_7d", F.col("pct_change_7d").cast(DoubleType())) \
       .withColumn("price_btc", F.col("price_btc").cast(DoubleType())) \
       .withColumn("market_cap_usd", F.col("market_cap_usd").cast(DoubleType())) \
       .withColumn("volume_24h_usd", F.col("volume_24h_usd").cast(DoubleType())) \
       .withColumn("circulating_supply", F.col("circulating_supply").cast(DoubleType())) \
       .withColumn("total_supply", F.col("total_supply").cast(DoubleType())) \
       .withColumn("max_supply", F.col("max_supply").cast(DoubleType())) \
       .withColumn("snapshot_time", F.to_timestamp("snapshot_time")) \
       .withColumn("ingested_at", F.to_timestamp("ingested_at"))

# Add partition column + hour lineage column (not a partition in silver)
df = df.withColumn("par_day", F.lit(par_day)) \
       .withColumn("hour", F.lit(par_hour))

# Dedup by coin_id + snapshot_time (keep latest ingested_at)
window = Window.partitionBy("coin_id", "snapshot_time").orderBy(F.col("ingested_at").desc())
df = df.withColumn("_rank", F.row_number().over(window)) \
       .filter(F.col("_rank") == 1) \
       .drop("_rank")

# --- Validation + Quarantine ---
valid_condition = (
    F.col("coin_id").isNotNull()
    & F.col("price_usd").isNotNull()
    & (F.col("price_usd") >= 0)
    & F.col("symbol").isNotNull()
)

good_df = df.filter(valid_condition)
bad_df = df.filter(~valid_condition)

# MERGE good records into silver Delta table
if good_df.count() > 0:
    if DeltaTable.isDeltaTable(spark, silver_path):
        delta_table = DeltaTable.forPath(spark, silver_path)
        delta_table.alias("target").merge(
            good_df.alias("source"),
            "target.coin_id = source.coin_id AND target.snapshot_time = source.snapshot_time"
        ).whenMatchedUpdateAll() \
         .whenNotMatchedInsertAll() \
         .execute()
        print(f"Merged {good_df.count()} good records into silver Delta table")
    else:
        good_df.write.format("delta").partitionBy("par_day").save(silver_path)
        print(f"Created silver Delta table with {good_df.count()} records")
else:
    print("No valid records to merge into silver")

# Write bad records to quarantine
if bad_df.count() > 0:
    bad_df = bad_df.withColumn("quarantine_reason",
        F.when(F.col("coin_id").isNull(), "null_coin_id")
         .when(F.col("price_usd").isNull(), "null_price_usd")
         .when(F.col("price_usd") < 0, "negative_price")
         .when(F.col("symbol").isNull(), "null_symbol")
         .otherwise("unknown"))
    bad_df = bad_df.withColumn("quarantined_at", F.current_timestamp())

    # MERGE into quarantine Delta (dedup by natural key)
    if DeltaTable.isDeltaTable(spark, quarantine_path):
        qt = DeltaTable.forPath(spark, quarantine_path)
        qt.alias("target").merge(
            bad_df.alias("source"),
            "target.coin_id = source.coin_id AND target.snapshot_time = source.snapshot_time AND target.par_day = source.par_day"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    else:
        bad_df.write.format("delta").partitionBy("par_day").save(quarantine_path)

    quarantine_count = bad_df.count()
    reasons = [row.quarantine_reason for row in bad_df.select("quarantine_reason").distinct().collect()]
    print(f"Quarantined {quarantine_count} records: {reasons}")

    # Write QUARANTINE# record to DynamoDB
    ddb = boto3.client("dynamodb")
    ddb.put_item(TableName=table_name, Item={
        "PK": {"S": f"PIPELINE#{pipeline_id}"},
        "SK": {"S": f"QUARANTINE#{par_day}#{par_hour}"},
        "data": {"S": json.dumps({
            "pipelineId": pipeline_id,
            "date": par_day,
            "hour": par_hour,
            "count": quarantine_count,
            "quarantinePath": quarantine_path,
            "reasons": reasons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })},
        "ttl": {"N": str(int(time.time()) + 86400 * 30)},
    })

job.commit()
