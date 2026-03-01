"""Custom evaluator Lambda for medallion pipeline traits.

Handles three evaluation types:
- source-freshness: Check if bronze data is recent enough for a given hour
- record-count: Check if minimum number of objects exist for a given hour
- upstream-dependency: Check if upstream silver pipeline completed for the hour

Includes chaos-awareness (CHAOS#BLOCK, CHAOS#SLOW, CHAOS#FALSE_PASS checks)
and writes EVAL# observability records for each evaluation.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")
ddb_client = boto3.client("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "medallion-interlock")


def handler(event, context):
    """API Gateway proxy handler — routes to the correct evaluator.

    The interlock HTTPRunner sends EvaluatorInput:
        {"pipelineId": "...", "traitType": "...", "config": {...}}
    The trait config is nested under "config".  scheduleID (e.g. "h15")
    may be injected by the orchestrator; we parse it into an integer hour.
    """
    path = event.get("rawPath", "") or event.get("path", "")
    body = json.loads(event.get("body", "{}"))

    # Extract nested config from EvaluatorInput format.
    config = body.get("config", body)
    pipeline_id = body.get("pipelineId", body.get("pipelineID",
                   config.get("pipelineId", config.get("pipelineID", "unknown"))))
    trait_type = body.get("traitType", "")

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

    # Check chaos conditions
    chaos_result = _check_chaos(pipeline_id, trait_type, config)
    if chaos_result is not None:
        _write_eval_record(pipeline_id, schedule_id or "unknown", trait_type, chaos_result)
        return _response(200, chaos_result)

    # Inject pipelineID into config for evaluators that need it.
    config["pipelineID"] = pipeline_id

    evaluators = {
        "/evaluate/source-freshness": evaluate_source_freshness,
        "/evaluate/record-count": evaluate_record_count,
        "/evaluate/upstream-dependency": evaluate_upstream_dependency,
        "/evaluate/hour-complete": evaluate_hour_complete,
    }

    fn = evaluators.get(path)
    if fn is None:
        return _response(404, {"error": f"unknown evaluator path: {path}"})

    try:
        result = fn(config)
        _write_eval_record(pipeline_id, schedule_id or "unknown", trait_type, result)
        return _response(200, result)
    except Exception as e:
        logger.exception("evaluator error")
        return _response(500, {"error": str(e)})


def _check_chaos(pipeline_id, trait_type, config):
    """Check for chaos conditions: block, slow, false-pass."""
    try:
        # Check CHAOS#BLOCK
        resp = ddb_client.get_item(
            TableName=TABLE_NAME,
            Key={"PK": {"S": f"CHAOS#BLOCK#{pipeline_id}"}, "SK": {"S": "ACTIVE"}},
        )
        if "Item" in resp:
            logger.warning("chaos: eval-block active for %s", pipeline_id)
            return {
                "status": "FAIL",
                "reason": f"chaos eval-block active for {pipeline_id}",
                "value": {"chaosScenario": "eval-block"},
            }

        # Check CHAOS#SLOW
        resp = ddb_client.get_item(
            TableName=TABLE_NAME,
            Key={"PK": {"S": f"CHAOS#SLOW#{pipeline_id}"}, "SK": {"S": "ACTIVE"}},
        )
        if "Item" in resp:
            delay = 25  # Near Lambda timeout (30s)
            logger.warning("chaos: eval-slow active for %s, sleeping %ds", pipeline_id, delay)
            time.sleep(delay)

        # Check CHAOS#FALSE_PASS
        resp = ddb_client.get_item(
            TableName=TABLE_NAME,
            Key={"PK": {"S": f"CHAOS#FALSE_PASS#{pipeline_id}"}, "SK": {"S": "ACTIVE"}},
        )
        if "Item" in resp:
            logger.warning("chaos: eval-false-pass active for %s", pipeline_id)
            return {
                "status": "PASS",
                "value": {"chaosScenario": "eval-false-pass", "realStatus": "UNKNOWN"},
            }
    except ClientError:
        logger.exception("error checking chaos conditions")
    return None


def _write_eval_record(pipeline_id, schedule_id, trait_type, result):
    """Write an EVAL# observability record to DynamoDB."""
    try:
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        date_str = now.strftime("%Y%m%d")
        ttl = int(now.timestamp()) + (30 * 86400)

        ddb_client.put_item(
            TableName=TABLE_NAME,
            Item={
                "PK": {"S": f"PIPELINE#{pipeline_id}"},
                "SK": {"S": f"EVAL#{date_str}#{schedule_id}#{trait_type}"},
                "GSI1PK": {"S": "EVALS"},
                "GSI1SK": {"S": f"{ts}#{pipeline_id}"},
                "traitType": {"S": trait_type},
                "status": {"S": result.get("status", "UNKNOWN")},
                "value": {"S": json.dumps(result.get("value", {}))},
                "reason": {"S": result.get("reason", "")},
                "evaluatedAt": {"S": ts},
                "ttl": {"N": str(ttl)},
            },
        )
    except ClientError:
        logger.exception("failed to write EVAL record for %s", pipeline_id)


def evaluate_source_freshness(config):
    """Check newest object in the date/hour-scoped S3 prefix is within maxAgeSeconds."""
    bucket = config["bucket"]
    prefix = config["prefix"]
    max_age = config.get("maxAgeSeconds", 900)
    hour = config.get("hour")
    date = config.get("date", datetime.now(timezone.utc).strftime("%Y%m%d")).replace("-", "")

    if hour is not None:
        scoped_prefix = f"{prefix}par_day={date}/par_hour={hour:02d}/"
    else:
        scoped_prefix = f"{prefix}par_day={date}/"

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
    date = config.get("date", datetime.now(timezone.utc).strftime("%Y%m%d")).replace("-", "")

    if hour is not None:
        scoped_prefix = f"{prefix}par_day={date}/par_hour={hour:02d}/"
    else:
        scoped_prefix = f"{prefix}par_day={date}/"

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


def evaluate_hour_complete(config):
    """Check if the per-hour record count has reached the expected threshold.

    Reads the atomic counter written by increment_hour_record_count() in the
    ingestion lambdas.  SENSOR#record-count#{par_day}#{par_hour} stores a
    running count that is atomically incremented on each ingestion batch.
    """
    pipeline_id = config.get("pipelineID", "unknown")
    expected_count = config.get("expectedCount", 1)
    hour = config.get("hour")
    date = config.get("date", datetime.now(timezone.utc).strftime("%Y%m%d")).replace("-", "")

    if hour is None:
        return {
            "status": "FAIL",
            "reason": "hour-complete evaluator requires an hour",
            "value": {"expectedCount": expected_count},
        }

    par_hour = f"{hour:02d}"
    sk = f"SENSOR#record-count#{date}#{par_hour}"

    resp = ddb_client.get_item(
        TableName=TABLE_NAME,
        Key={
            "PK": {"S": f"PIPELINE#{pipeline_id}"},
            "SK": {"S": sk},
        },
        ConsistentRead=True,
    )

    item = resp.get("Item")
    if not item:
        return {
            "status": "FAIL",
            "reason": f"no record-count sensor for {pipeline_id} {date}/{par_hour}",
            "value": {"count": 0, "expectedCount": expected_count},
        }

    count = int(item.get("count", {}).get("N", "0"))
    if count >= expected_count:
        return {
            "status": "PASS",
            "value": {"count": count, "expectedCount": expected_count},
        }

    return {
        "status": "FAIL",
        "reason": f"record count {count} < expected {expected_count}",
        "value": {"count": count, "expectedCount": expected_count},
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
