"""Gold GH Archive ETL — silver Delta → gold Delta (aggregations).

Produces hourly event counts by type, top-10 repos, and language distribution.
"""

import sys
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, countDistinct, lit, current_timestamp,
    hour as spark_hour, desc, row_number, split,
)
from pyspark.sql.window import Window
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
hour_val = int(args["hour"])

silver_path = f"s3://{bucket}/silver/gharchive/"
gold_path = f"s3://{bucket}/gold/gharchive/"

df_silver = spark.read.format("delta").load(silver_path).filter(col("dt") == date)

# --- Hourly event counts by type ---
df_hourly = (
    df_silver
    .groupBy("dt", spark_hour("created_at").alias("hour"), "event_type")
    .agg(
        count("*").alias("event_count"),
        countDistinct("actor_login").alias("unique_actors"),
    )
    .withColumn("metric_type", lit("hourly_by_type"))
    .withColumn("computed_at", current_timestamp())
)

# --- Top-10 repos by event count ---
w = Window.partitionBy("dt").orderBy(desc("event_count"))
df_top_repos = (
    df_silver
    .groupBy("dt", "repo_name")
    .agg(count("*").alias("event_count"))
    .withColumn("rank", row_number().over(w))
    .filter(col("rank") <= 10)
    .withColumn("metric_type", lit("top_repos"))
    .withColumn("computed_at", current_timestamp())
)

# --- Organization activity ---
df_org_activity = (
    df_silver
    .filter(col("org_login").isNotNull())
    .groupBy("dt", "org_login")
    .agg(
        count("*").alias("event_count"),
        countDistinct("actor_login").alias("unique_actors"),
        countDistinct("repo_name").alias("unique_repos"),
    )
    .withColumn("metric_type", lit("org_activity"))
    .withColumn("computed_at", current_timestamp())
)

# Write all aggregations to gold — each table needs its own merge key
aggregations = [
    ("hourly_by_type", df_hourly, "target.dt = source.dt AND target.hour = source.hour AND target.event_type = source.event_type"),
    ("top_repos", df_top_repos, "target.dt = source.dt AND target.repo_name = source.repo_name"),
    ("org_activity", df_org_activity, "target.dt = source.dt AND target.org_login = source.org_login"),
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
