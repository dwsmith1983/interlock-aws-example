"""Silver GH Archive ETL — bronze JSONL.gz → silver Delta table.

Reads raw GH Archive events, decompresses, flattens actor/repo/payload,
deduplicates by event id, and MERGE INTO the silver Delta table.
"""

import sys
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, current_timestamp, lit
from pyspark.sql.types import LongType, StringType
from delta.tables import DeltaTable

args = getResolvedOptions(sys.argv, ["JOB_NAME", "source", "tier", "bucket", "date", "hour"])

spark = (
    SparkSession.builder
    .appName(args["JOB_NAME"])
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    .getOrCreate()
)

bucket = args["bucket"]
date = args["date"]
hour = int(args["hour"])

bronze_path = f"s3://{bucket}/bronze/gharchive/dt={date}/hh={hour:02d}/"
silver_path = f"s3://{bucket}/silver/gharchive/"

# Read bronze JSONL (Spark handles .gz decompression automatically)
df_raw = spark.read.json(bronze_path)

# Flatten and enforce types
df_clean = (
    df_raw
    .select(
        col("id").cast(LongType()).alias("event_id"),
        col("type").alias("event_type"),
        col("public").alias("is_public"),
        to_timestamp(col("created_at")).alias("created_at"),
        col("actor.id").cast(LongType()).alias("actor_id"),
        col("actor.login").alias("actor_login"),
        col("repo.id").cast(LongType()).alias("repo_id"),
        col("repo.name").alias("repo_name"),
        col("org.id").cast(LongType()).alias("org_id"),
        col("org.login").alias("org_login"),
    )
    .filter(col("event_id").isNotNull())
    .dropDuplicates(["event_id"])
    .withColumn("ingested_at", current_timestamp())
    .withColumn("dt", lit(date))
)

# MERGE INTO silver Delta table
if DeltaTable.isDeltaTable(spark, silver_path):
    delta_table = DeltaTable.forPath(spark, silver_path)
    (
        delta_table.alias("target")
        .merge(
            df_clean.alias("source"),
            "target.event_id = source.event_id",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
else:
    df_clean.write.format("delta").partitionBy("dt").mode("overwrite").save(silver_path)

spark.stop()
