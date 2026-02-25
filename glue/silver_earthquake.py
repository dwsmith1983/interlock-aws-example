"""Silver ETL: Bronze earthquake JSONL -> Silver Delta table.

Reads bronze JSONL files for the target par_day/par_hour, flattens GeoJSON,
deduplicates by earthquake_id (keeping latest by updated_time), and upserts
into the silver Delta table via MERGE.
"""

import sys

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
    TimestampType,
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

# Add partition columns
df = df.withColumn("par_day", F.lit(par_day)) \
       .withColumn("par_hour", F.lit(par_hour))

# Dedup by earthquake_id, keeping the latest by updated_time
window = Window.partitionBy("earthquake_id").orderBy(F.col("updated_time").desc())
df = df.withColumn("_rank", F.row_number().over(window)) \
       .filter(F.col("_rank") == 1) \
       .drop("_rank")

# Filter out records with null earthquake_id
df = df.filter(F.col("earthquake_id").isNotNull())

# MERGE into silver Delta table
if DeltaTable.isDeltaTable(spark, silver_path):
    delta_table = DeltaTable.forPath(spark, silver_path)
    delta_table.alias("target").merge(
        df.alias("source"),
        "target.earthquake_id = source.earthquake_id"
    ).whenMatchedUpdateAll() \
     .whenNotMatchedInsertAll() \
     .execute()
    print(f"Merged {df.count()} records into silver Delta table")
else:
    df.write.format("delta").partitionBy("par_day").save(silver_path)
    print(f"Created silver Delta table with {df.count()} records")

job.commit()
