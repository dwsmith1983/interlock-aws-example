"""Compact observability: JSONL staging -> Delta table.

Reads staged JSONL observability events for the target par_day, deduplicates
by eventId, and MERGE-inserts into the pipeline_events Delta table.
"""

import sys
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from delta.tables import DeltaTable
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import (
    MapType,
    StringType,
    StructField,
    StructType,
)

args = getResolvedOptions(sys.argv, ["JOB_NAME", "bucket"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

bucket = args["bucket"]

# par_day defaults to today's date if not provided or empty
par_day = args.get("par_day", "").replace("-", "")
if not par_day:
    par_day = datetime.now(timezone.utc).strftime("%Y%m%d")

staging_path = f"s3://{bucket}/observability/staging/par_day={par_day}/"
delta_path = f"s3://{bucket}/observability/pipeline_events/"

# Read staged JSONL
schema = StructType([
    StructField("eventId", StringType(), True),
    StructField("recordType", StringType(), True),
    StructField("eventType", StringType(), True),
    StructField("pipelineId", StringType(), True),
    StructField("scheduleId", StringType(), True),
    StructField("runId", StringType(), True),
    StructField("date", StringType(), True),
    StructField("status", StringType(), True),
    StructField("message", StringType(), True),
    StructField("detail", MapType(StringType(), StringType()), True),
    StructField("timestamp", StringType(), True),
])

df = spark.read.schema(schema).json(staging_path)

if df.rdd.isEmpty():
    print(f"No staging data at {staging_path}, skipping")
    job.commit()
    sys.exit(0)

# Cast timestamp string to proper type
df = df.withColumn("timestamp", F.to_timestamp("timestamp"))

# Add partition column
df = df.withColumn("par_day", F.lit(par_day))

# Convert detail map to JSON string for Delta storage
df = df.withColumn("detail_json",
    F.when(F.col("detail").isNotNull(), F.to_json("detail"))
     .otherwise(F.lit(None)))
df = df.drop("detail")

# Dedup by eventId (keep first occurrence)
df = df.dropDuplicates(["eventId"])

# Filter out null eventIds
df = df.filter(F.col("eventId").isNotNull())

# MERGE into Delta table (insert-only — events are immutable)
if DeltaTable.isDeltaTable(spark, delta_path):
    delta_table = DeltaTable.forPath(spark, delta_path)
    delta_table.alias("target").merge(
        df.alias("source"),
        "target.eventId = source.eventId AND target.par_day = source.par_day"
    ).whenNotMatchedInsertAll().execute()
    print(f"Merged {df.count()} events into Delta table")
else:
    df.write.format("delta").partitionBy("par_day").save(delta_path)
    print(f"Created Delta table with {df.count()} events")

job.commit()
