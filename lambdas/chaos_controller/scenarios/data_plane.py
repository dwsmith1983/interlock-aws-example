"""Category 2: Data Plane Chaos — corrupting/removing S3 data.

Scenarios:
- delete-bronze: Delete a recent bronze S3 object
- corrupt-bronze: Overwrite a bronze file with invalid JSON
- empty-bronze: Write a 0-byte file to bronze partition
- corrupt-delta-log: Delete a Delta log file in silver
- wrong-partition: Write bronze data with tomorrow's par_day
"""

import json
import logging
import random
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger(__name__)

s3 = boto3.client("s3")

SOURCES = ["earthquake", "crypto"]


def delete_bronze(ctx):
    """Delete a recent bronze S3 object from the current hour."""
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    prefix = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/"
    obj = _pick_random_object(bucket, prefix)
    if not obj:
        return {"skipped": True, "reason": f"no objects at {prefix}"}

    s3.delete_object(Bucket=bucket, Key=obj)
    logger.info("deleted bronze object: s3://%s/%s", bucket, obj)
    return {"action": "deleted", "key": obj}


def corrupt_bronze(ctx):
    """Overwrite a bronze file with invalid JSON."""
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    prefix = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/"
    obj = _pick_random_object(bucket, prefix)
    if not obj:
        return {"skipped": True, "reason": f"no objects at {prefix}"}

    corrupt_content = b'{"corrupt": true, "invalid_json_missing_close_brace'
    s3.put_object(Bucket=bucket, Key=obj, Body=corrupt_content, ContentType="application/json")
    logger.info("corrupted bronze object: s3://%s/%s", bucket, obj)
    return {"action": "corrupted", "key": obj}


def empty_bronze(ctx):
    """Write a 0-byte file to a bronze partition."""
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    key = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/chaos_empty_{now.strftime('%H%M%S')}.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body=b"", ContentType="application/json")
    logger.info("wrote empty bronze file: s3://%s/%s", bucket, key)
    return {"action": "empty_write", "key": key}


def corrupt_delta_log(ctx):
    """Delete or rename a Delta log file in the silver directory."""
    bucket = ctx["bucket_name"]
    source = _source_for_pipeline(ctx["pipeline_id"])

    prefix = f"silver/{source}/_delta_log/"
    obj = _pick_random_object(bucket, prefix)
    if not obj:
        return {"skipped": True, "reason": f"no delta log files at {prefix}"}

    # Rename (copy + delete) to preserve data but break Delta
    backup_key = obj + ".chaos_backup"
    s3.copy_object(Bucket=bucket, CopySource=f"{bucket}/{obj}", Key=backup_key)
    s3.delete_object(Bucket=bucket, Key=obj)
    logger.info("corrupted delta log: moved %s to %s", obj, backup_key)
    return {"action": "delta_log_corrupted", "originalKey": obj, "backupKey": backup_key}


def wrong_partition(ctx):
    """Write bronze data with par_day from tomorrow."""
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    tomorrow = (now + timedelta(days=1)).strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    content = json.dumps({"chaos": True, "scenario": "wrong-partition", "timestamp": now.isoformat()}).encode()
    key = f"bronze/{source}/par_day={tomorrow}/par_hour={par_hour}/chaos_wrong_partition.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/json")
    logger.info("wrote wrong-partition data: s3://%s/%s", bucket, key)
    return {"action": "wrong_partition", "key": key, "wrongParDay": tomorrow}


def _source_for_pipeline(pipeline_id):
    """Extract source name from pipeline ID."""
    if "earthquake" in pipeline_id:
        return "earthquake"
    return "crypto"


def _pick_random_object(bucket, prefix):
    """Pick a random object from the given S3 prefix."""
    try:
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=20)
        contents = resp.get("Contents", [])
        if not contents:
            return None
        return random.choice(contents)["Key"]
    except Exception:
        logger.exception("error listing objects at %s", prefix)
        return None
