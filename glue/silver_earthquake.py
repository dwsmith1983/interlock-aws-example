"""Silver ETL: Bronze earthquake JSONL -> Silver Delta table.

Reads bronze JSONL files for the target par_day/par_hour, flattens GeoJSON,
deduplicates by earthquake_id (keeping latest by updated_time), validates
records, quarantines bad data, and upserts good data into the silver Delta
table via MERGE.
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
    BooleanType,
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
table_name = args["table_name"]
par_day = args["par_day"].replace("-", "")
par_hour = args["par_hour"]
pipeline_id = "earthquake-silver"

bronze_path = f"s3://{bucket}/bronze/{source}/par_day={par_day}/par_hour={par_hour}/"
silver_path = f"s3://{bucket}/silver/{source}/"
quarantine_path = f"s3://{bucket}/quarantine/{source}/"

# Read bronze JSONL
schema = StructType([
    StructField("earthquake_id", StringType(), True),
    StructField("magnitude", DoubleType(), True),
    StructField("place", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("updated_time", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("review_status", StringType(), True),
    StructField("is_tsunami", BooleanType(), True),
    StructField("significance", IntegerType(), True),
    StructField("network", StringType(), True),
    StructField("num_stations", IntegerType(), True),
    StructField("min_distance_deg", DoubleType(), True),
    StructField("rms", DoubleType(), True),
    StructField("azimuthal_gap", DoubleType(), True),
    StructField("magnitude_type", StringType(), True),
    StructField("alert_level", StringType(), True),
    StructField("longitude", DoubleType(), True),
    StructField("latitude", DoubleType(), True),
    StructField("depth_km", DoubleType(), True),
    StructField("ingested_at", StringType(), True),
])

df = spark.read.schema(schema).json(bronze_path)

if df.rdd.isEmpty():
    print(f"No data found at {bronze_path}, skipping")
    job.commit()
    sys.exit(0)

# Cast timestamp strings
df = df.withColumn("event_time", F.to_timestamp("event_time")) \
       .withColumn("updated_time", F.to_timestamp("updated_time")) \
       .withColumn("ingested_at", F.to_timestamp("ingested_at"))

# Add partition column + hour lineage column (not a partition in silver)
df = df.withColumn("par_day", F.lit(par_day)) \
       .withColumn("hour", F.lit(par_hour))

# Dedup by earthquake_id, keeping the latest by updated_time
window = Window.partitionBy("earthquake_id").orderBy(F.col("updated_time").desc())
df = df.withColumn("_rank", F.row_number().over(window)) \
       .filter(F.col("_rank") == 1) \
       .drop("_rank")

# --- Validation + Quarantine ---
valid_condition = (
    F.col("earthquake_id").isNotNull()
    & F.col("magnitude").isNotNull()
    & F.col("longitude").between(-180, 180)
    & F.col("latitude").between(-90, 90)
)

good_df = df.filter(valid_condition)
bad_df = df.filter(~valid_condition)

# MERGE good records into silver Delta table
if good_df.count() > 0:
    if DeltaTable.isDeltaTable(spark, silver_path):
        delta_table = DeltaTable.forPath(spark, silver_path)
        delta_table.alias("target").merge(
            good_df.alias("source"),
            "target.earthquake_id = source.earthquake_id"
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
        F.when(F.col("earthquake_id").isNull(), "null_id")
         .when(F.col("magnitude").isNull(), "null_magnitude")
         .when(~F.col("longitude").between(-180, 180), "invalid_longitude")
         .when(~F.col("latitude").between(-90, 90), "invalid_latitude")
         .otherwise("unknown"))
    bad_df = bad_df.withColumn("quarantined_at", F.current_timestamp())

    # MERGE into quarantine Delta (dedup by natural key)
    if DeltaTable.isDeltaTable(spark, quarantine_path):
        qt = DeltaTable.forPath(spark, quarantine_path)
        qt.alias("target").merge(
            bad_df.alias("source"),
            "target.earthquake_id = source.earthquake_id AND target.par_day = source.par_day"
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
