"""Gold ETL: Silver earthquake Delta -> 4 Gold aggregation tables.

Reads all silver earthquake data for the target date and produces:
1. hourly_summary: event_count, avg/max magnitude, depth stats per hour
2. daily_summary: total_events, avg/max magnitude, distinct types/networks per day
3. magnitude_distribution: event counts bucketed by magnitude range per day
4. geographic_hotspots: event counts by 10-degree lat/lon grid per day

All outputs use Delta MERGE for idempotent re-runs.
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from delta.tables import DeltaTable
from pyspark.context import SparkContext
from pyspark.sql import functions as F

args = getResolvedOptions(sys.argv, ["JOB_NAME", "bucket", "table_name", "source", "tier",
                                       "par_day"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

bucket = args["bucket"]
par_day = args["par_day"].replace("-", "")

silver_path = f"s3://{bucket}/silver/earthquake/"
gold_base = f"s3://{bucket}/gold/earthquake"

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


# 1. Hourly Summary
hourly = silver_df.groupBy("par_day", "hour").agg(
    F.count("*").alias("event_count"),
    F.avg("magnitude").alias("avg_magnitude"),
    F.max("magnitude").alias("max_magnitude"),
    F.min("magnitude").alias("min_magnitude"),
    F.avg("depth_km").alias("avg_depth_km"),
    F.max("depth_km").alias("max_depth_km"),
    F.sum(F.when(F.col("is_tsunami") == True, 1).otherwise(0)).alias("tsunami_count"),
    F.sum(F.when(F.col("magnitude") >= 4.0, 1).otherwise(0)).alias("significant_count"),
)

hourly_path = f"{gold_base}/hourly_summary/"
merge_or_create(hourly, hourly_path,
                "target.par_day = source.par_day AND target.hour = source.hour")
print(f"Wrote {hourly.count()} hourly_summary records")

# 2. Daily Summary
daily = silver_df.groupBy("par_day").agg(
    F.count("*").alias("total_events"),
    F.avg("magnitude").alias("avg_magnitude"),
    F.max("magnitude").alias("max_magnitude"),
    F.min("magnitude").alias("min_magnitude"),
    F.countDistinct("event_type").alias("distinct_event_types"),
    F.countDistinct("network").alias("distinct_networks"),
    F.sum(F.when(F.col("is_tsunami") == True, 1).otherwise(0)).alias("tsunami_count"),
    F.sum(F.when(F.col("magnitude") >= 4.0, 1).otherwise(0)).alias("significant_count"),
)

daily_path = f"{gold_base}/daily_summary/"
merge_or_create(daily, daily_path, "target.par_day = source.par_day")
print(f"Wrote {daily.count()} daily_summary records")

# 3. Magnitude Distribution (bucketed by ranges: 0-1, 1-2, 2-3, 3-4, 4-5, 5+)
mag_dist = silver_df.withColumn(
    "magnitude_bucket",
    F.when(F.col("magnitude") < 1, "0-1")
     .when(F.col("magnitude") < 2, "1-2")
     .when(F.col("magnitude") < 3, "2-3")
     .when(F.col("magnitude") < 4, "3-4")
     .when(F.col("magnitude") < 5, "4-5")
     .otherwise("5+")
).groupBy("par_day", "magnitude_bucket").agg(
    F.count("*").alias("event_count"),
    F.avg("depth_km").alias("avg_depth_km"),
    F.avg("magnitude").alias("avg_magnitude"),
)

mag_path = f"{gold_base}/magnitude_distribution/"
merge_or_create(mag_dist, mag_path,
                "target.par_day = source.par_day AND target.magnitude_bucket = source.magnitude_bucket")
print(f"Wrote {mag_dist.count()} magnitude_distribution records")

# 4. Geographic Hotspots (10-degree lat/lon grid)
geo = silver_df.filter(
    F.col("latitude").isNotNull() & F.col("longitude").isNotNull()
).withColumn(
    "lat_bucket", (F.floor(F.col("latitude") / 10) * 10).cast("int")
).withColumn(
    "lon_bucket", (F.floor(F.col("longitude") / 10) * 10).cast("int")
).groupBy("par_day", "lat_bucket", "lon_bucket").agg(
    F.count("*").alias("event_count"),
    F.avg("magnitude").alias("avg_magnitude"),
    F.max("magnitude").alias("max_magnitude"),
)

geo_path = f"{gold_base}/geographic_hotspots/"
merge_or_create(geo, geo_path,
                "target.par_day = source.par_day AND target.lat_bucket = source.lat_bucket AND target.lon_bucket = source.lon_bucket")
print(f"Wrote {geo.count()} geographic_hotspots records")

job.commit()
