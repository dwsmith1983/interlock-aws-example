"""Gold Open-Meteo ETL — silver Delta → gold Delta (aggregations).

Produces daily min/max/avg temperature per city and total precipitation.
"""

import sys
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, min as spark_min, max as spark_max, avg as spark_avg,
    sum as spark_sum, lit, current_timestamp,
)
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

silver_path = f"s3://{bucket}/silver/openmeteo/"
gold_path = f"s3://{bucket}/gold/openmeteo/"

df_silver = spark.read.format("delta").load(silver_path).filter(col("dt") == date)

# --- Daily weather summary per city ---
df_daily = (
    df_silver
    .groupBy("dt", "city", "latitude", "longitude")
    .agg(
        spark_min("temperature_celsius").alias("min_temp_c"),
        spark_max("temperature_celsius").alias("max_temp_c"),
        spark_avg("temperature_celsius").alias("avg_temp_c"),
        spark_sum("precipitation_mm").alias("total_precipitation_mm"),
        spark_avg("relative_humidity").alias("avg_humidity"),
        spark_avg("wind_speed_kmh").alias("avg_wind_speed_kmh"),
        count("*").alias("observation_count"),
    )
    .withColumn("metric_type", lit("daily_city_summary"))
    .withColumn("computed_at", current_timestamp())
)

# --- Cross-city comparison ---
df_cross_city = (
    df_silver
    .groupBy("dt")
    .agg(
        spark_min("temperature_celsius").alias("global_min_temp_c"),
        spark_max("temperature_celsius").alias("global_max_temp_c"),
        spark_avg("temperature_celsius").alias("global_avg_temp_c"),
        spark_sum("precipitation_mm").alias("global_total_precipitation_mm"),
        count("*").alias("total_observations"),
    )
    .withColumn("metric_type", lit("daily_global_summary"))
    .withColumn("computed_at", current_timestamp())
)

# Write aggregations to gold — each table needs its own merge key
aggregations = [
    ("daily_city", df_daily, "target.dt = source.dt AND target.city = source.city"),
    ("daily_global", df_cross_city, "target.dt = source.dt"),
]

for name, df, merge_key in aggregations:
    out_path = f"{gold_path}{name}/"
    if DeltaTable.isDeltaTable(spark, out_path):
        delta_table = DeltaTable.forPath(spark, out_path)
        (
            delta_table.alias("target")
            .merge(df.alias("source"), merge_key)
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        df.write.format("delta").partitionBy("dt").mode("overwrite").save(out_path)

spark.stop()
