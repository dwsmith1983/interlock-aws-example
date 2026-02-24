"""Custom evaluator Lambda for medallion pipeline traits.

Handles three evaluation types:
- source-freshness: Check if bronze data is recent enough for a given hour
- record-count: Check if minimum number of objects exist for a given hour
- upstream-dependency: Check if upstream silver pipeline completed for the hour
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "medallion-interlock")


def handler(event, context):
    """API Gateway proxy handler — routes to the correct evaluator.

    The interlock HTTPRunner sends EvaluatorInput:
        {"pipelineID": "...", "traitType": "...", "config": {...}}
    The trait config is nested under "config".  scheduleID (e.g. "h15")
    may be injected by the orchestrator; we parse it into an integer hour.
    """
    path = event.get("rawPath", "") or event.get("path", "")
    body = json.loads(event.get("body", "{}"))

    # Extract nested config from EvaluatorInput format.
    config = body.get("config", body)

    # Derive hour from scheduleID (e.g. "h15" → 15) if present.
    # Traits with dateOnly=true opt out of hour scoping (e.g. Delta tables
    # partitioned by date only, not by hour).
    schedule_id = config.pop("scheduleID", None)
    date_only = config.pop("dateOnly", False)
    if schedule_id and schedule_id.startswith("h") and "hour" not in config and not date_only:
        try:
            config["hour"] = int(schedule_id[1:])
        except ValueError:
            pass

    evaluators = {
        "/evaluate/source-freshness": evaluate_source_freshness,
        "/evaluate/record-count": evaluate_record_count,
        "/evaluate/upstream-dependency": evaluate_upstream_dependency,
    }

    fn = evaluators.get(path)
    if fn is None:
        return _response(404, {"error": f"unknown evaluator path: {path}"})

    try:
        result = fn(config)
        return _response(200, result)
    except Exception as e:
        logger.exception("evaluator error")
        return _response(500, {"error": str(e)})


def evaluate_source_freshness(config):
    """Check newest object in the date/hour-scoped S3 prefix is within maxAgeSeconds."""
    bucket = config["bucket"]
    prefix = config["prefix"]
    max_age = config.get("maxAgeSeconds", 900)
    hour = config.get("hour")
    date = config.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    if hour is not None:
        scoped_prefix = f"{prefix}dt={date}/hh={hour:02d}/"
    else:
        scoped_prefix = f"{prefix}dt={date}/"

    newest = _newest_object_time(bucket, scoped_prefix)
    if newest is None:
        return {
            "status": "FAIL",
            "reason": f"no objects found at s3://{bucket}/{scoped_prefix}",
            "value": {"objectCount": 0},
        }

    age_seconds = (datetime.now(timezone.utc) - newest).total_seconds()
    if age_seconds > max_age:
        return {
            "status": "FAIL",
            "reason": f"newest object is {int(age_seconds)}s old (max {max_age}s)",
            "value": {"ageSeconds": int(age_seconds), "maxAgeSeconds": max_age},
        }

    return {
        "status": "PASS",
        "value": {"ageSeconds": int(age_seconds), "maxAgeSeconds": max_age},
    }


def evaluate_record_count(config):
    """Check that at least minObjects exist in the scoped S3 prefix."""
    bucket = config["bucket"]
    prefix = config["prefix"]
    min_objects = config.get("minObjects", 1)
    hour = config.get("hour")
    date = config.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    if hour is not None:
        scoped_prefix = f"{prefix}dt={date}/hh={hour:02d}/"
    else:
        scoped_prefix = f"{prefix}dt={date}/"

    count = _count_objects(bucket, scoped_prefix)
    if count < min_objects:
        return {
            "status": "FAIL",
            "reason": f"found {count} objects, need at least {min_objects}",
            "value": {"objectCount": count, "minObjects": min_objects},
        }

    return {
        "status": "PASS",
        "value": {"objectCount": count, "minObjects": min_objects},
    }


def evaluate_upstream_dependency(config):
    """Check if the upstream silver pipeline completed for this hour.

    Queries the interlock DynamoDB table for the RunLog entry.
    Retries up to 3 times with 1s backoff for timing races.
    """
    table_name = config.get("tableName", TABLE_NAME)
    upstream = config["upstreamPipeline"]
    date = config.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    hour = config.get("hour")
    schedule_id = f"h{hour:02d}" if hour is not None else "daily"

    table = ddb.Table(table_name)
    pk = f"PIPELINE#{upstream}"
    sk = f"RUNLOG#{date}#{schedule_id}"

    for attempt in range(3):
        resp = table.get_item(Key={"PK": pk, "SK": sk}, ConsistentRead=True)
        item = resp.get("Item")
        if item:
            data = json.loads(item.get("data", "{}"))
            status = data.get("status", "")
            if status == "COMPLETED":
                return {
                    "status": "PASS",
                    "value": {"upstreamPipeline": upstream, "upstreamStatus": status},
                }
            return {
                "status": "FAIL",
                "reason": f"upstream {upstream} status is {status}, not COMPLETED",
                "value": {"upstreamPipeline": upstream, "upstreamStatus": status},
            }

        if attempt < 2:
            time.sleep(1)

    return {
        "status": "FAIL",
        "reason": f"no RunLog found for {upstream} schedule {schedule_id} on {date}",
        "value": {"upstreamPipeline": upstream, "scheduleID": schedule_id},
    }


def _newest_object_time(bucket, prefix):
    """Return the LastModified of the newest object under prefix, or None."""
    paginator = s3.get_paginator("list_objects_v2")
    newest = None
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            modified = obj["LastModified"]
            if newest is None or modified > newest:
                newest = modified
    return newest


def _count_objects(bucket, prefix):
    """Return count of objects under prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        count += len(page.get("Contents", []))
    return count


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
