"""Silver ETL: Bronze crypto JSONL -> Silver Delta table.

Reads bronze JSONL files for the target par_day/par_hour, casts string numerics
to doubles, deduplicates by coin_id+snapshot_time, and upserts into the silver
Delta table via MERGE.
"""

import sys

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
    StructField,
    StructType,
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
par_day = args["par_day"].replace("-", "")
par_hour = args["par_hour"]

bronze_path = f"s3://{bucket}/bronze/{source}/par_day={par_day}/par_hour={par_hour}/"
silver_path = f"s3://{bucket}/silver/{source}/"

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

# Filter out records with null coin_id
df = df.filter(F.col("coin_id").isNotNull())

# MERGE into silver Delta table
if DeltaTable.isDeltaTable(spark, silver_path):
    delta_table = DeltaTable.forPath(spark, silver_path)
    delta_table.alias("target").merge(
        df.alias("source"),
        "target.coin_id = source.coin_id AND target.snapshot_time = source.snapshot_time"
    ).whenMatchedUpdateAll() \
     .whenNotMatchedInsertAll() \
     .execute()
    print(f"Merged {df.count()} records into silver Delta table")
else:
    df.write.format("delta").partitionBy("par_day").save(silver_path)
    print(f"Created silver Delta table with {df.count()} records")

job.commit()
