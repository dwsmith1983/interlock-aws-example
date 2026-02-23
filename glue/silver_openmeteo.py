"""Silver Open-Meteo ETL — bronze JSONL → silver Delta table.

Reads raw Open-Meteo weather data, normalizes to Celsius, aligns UTC timestamps,
deduplicates by city+hour, and MERGE INTO the silver Delta table.
"""

import sys
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, current_timestamp, lit, explode
from pyspark.sql.types import DoubleType, StringType
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

bronze_path = f"s3://{bucket}/bronze/openmeteo/dt={date}/hh={hour:02d}/"
silver_path = f"s3://{bucket}/silver/openmeteo/"

# Read bronze JSONL
df_raw = spark.read.json(bronze_path)

# Extract current weather data — Open-Meteo nests under "current"
df_clean = (
    df_raw
    .select(
        col("city").alias("city"),
        col("latitude").cast(DoubleType()),
        col("longitude").cast(DoubleType()),
        col("current.time").alias("observation_time"),
        col("current.temperature_2m").cast(DoubleType()).alias("temperature_celsius"),
        col("current.relative_humidity_2m").cast(DoubleType()).alias("relative_humidity"),
        col("current.wind_speed_10m").cast(DoubleType()).alias("wind_speed_kmh"),
        col("current.precipitation").cast(DoubleType()).alias("precipitation_mm"),
        col("current.weather_code").alias("weather_code"),
        to_timestamp(col("fetched_at")).alias("fetched_at"),
    )
    .filter(col("city").isNotNull())
    .dropDuplicates(["city", "observation_time"])
    .withColumn("ingested_at", current_timestamp())
    .withColumn("dt", lit(date))
    .withColumn("hh", lit(f"{hour:02d}"))
)

# MERGE INTO silver Delta table
if DeltaTable.isDeltaTable(spark, silver_path):
    delta_table = DeltaTable.forPath(spark, silver_path)
    (
        delta_table.alias("target")
        .merge(
            df_clean.alias("source"),
            "target.city = source.city AND target.observation_time = source.observation_time",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
else:
    df_clean.write.format("delta").partitionBy("dt").mode("overwrite").save(silver_path)

spark.stop()
