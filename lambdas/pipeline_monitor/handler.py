"""DynamoDB Stream consumer — watches RUNLOG# changes and updates CONTROL# + JOBLOG# records.

Triggered by the same DynamoDB Stream as stream-router, with filter criteria
limiting invocations to records where SK begins with "RUNLOG#".
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

# 30-day TTL for JOBLOG records
RECORD_TTL_SECONDS = 30 * 24 * 60 * 60


def handler(event, context):
    processed = 0

    for record in event.get("Records", []):
        event_name = record.get("eventName", "")
        if event_name not in ("INSERT", "MODIFY"):
            continue

        new_image = record.get("dynamodb", {}).get("NewImage", {})
        if not new_image:
            continue

        sk = new_image.get("SK", {}).get("S", "")
        if not sk.startswith("RUNLOG#"):
            continue

        pk = new_image.get("PK", {}).get("S", "")
        pipeline_id = pk.replace("PIPELINE#", "") if pk.startswith("PIPELINE#") else pk

        # Parse the data JSON field for run details
        data_str = new_image.get("data", {}).get("S", "{}")
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            data = {}

        status = data.get("status", new_image.get("status", {}).get("S", ""))
        schedule_id = data.get("scheduleId", data.get("scheduleID", new_image.get("scheduleID", {}).get("S", "")))
        stage = data.get("stage", new_image.get("stage", {}).get("S", ""))
        timestamp = new_image.get("timestamp", {}).get("S", datetime.now(timezone.utc).isoformat())

        logger.info(
            "RUNLOG event: pipeline=%s schedule=%s status=%s stage=%s",
            pipeline_id, schedule_id, status, stage,
        )

        _update_control(pipeline_id, status, timestamp)
        _write_joblog(pipeline_id, schedule_id, stage, status, timestamp)
        processed += 1

    return {"statusCode": 200, "processed": processed}


def _update_control(pipeline_id, status, timestamp):
    """Update CONTROL# record based on run status."""
    key = {"PK": f"CONTROL#{pipeline_id}", "SK": "STATUS"}

    try:
        status_upper = status.upper()
        if status_upper == "COMPLETED":
            table.update_item(
                Key=key,
                UpdateExpression=(
                    "SET lastSuccessfulRun = :ts, consecutiveFailures = :zero, lastStatus = :st"
                ),
                ExpressionAttributeValues={
                    ":ts": timestamp,
                    ":zero": 0,
                    ":st": status_upper,
                },
            )
        elif status_upper == "FAILED":
            table.update_item(
                Key=key,
                UpdateExpression=(
                    "SET lastFailedRun = :ts, lastStatus = :st"
                    " ADD consecutiveFailures :one"
                ),
                ExpressionAttributeValues={
                    ":ts": timestamp,
                    ":st": status_upper,
                    ":one": 1,
                },
            )
        elif status_upper == "PENDING":
            table.update_item(
                Key=key,
                UpdateExpression="SET lastPendingRun = :ts, lastStatus = :st",
                ExpressionAttributeValues={
                    ":ts": timestamp,
                    ":st": status_upper,
                },
            )
        else:
            logger.warning("unknown RUNLOG status: %s for %s", status, pipeline_id)
    except Exception:
        logger.exception("failed to update CONTROL# for %s", pipeline_id)


def _write_joblog(pipeline_id, schedule_id, stage, status, timestamp):
    """Write a JOBLOG# record for every RUNLOG# change."""
    now = int(time.time())
    sk = f"{timestamp}#{schedule_id}#{status}"

    try:
        table.put_item(
            Item={
                "PK": f"JOBLOG#{pipeline_id}",
                "SK": sk,
                "GSI1PK": "JOBLOGS",
                "GSI1SK": f"{timestamp}#{pipeline_id}",
                "pipelineID": pipeline_id,
                "scheduleID": schedule_id,
                "stage": stage,
                "status": status,
                "timestamp": timestamp,
                "ttl": now + RECORD_TTL_SECONDS,
            }
        )
    except Exception:
        logger.exception("failed to write JOBLOG# for %s", pipeline_id)
