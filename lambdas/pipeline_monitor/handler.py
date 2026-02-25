"""DynamoDB Stream consumer — watches RUNLOG# changes and updates CONTROL# + JOBLOG# records.

Triggered by the same DynamoDB Stream as stream-router, with filter criteria
limiting invocations to records where SK begins with "RUNLOG#".
Also handles SNS lifecycle events for active chaos recovery.
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

TABLE_NAME = os.environ["TABLE_NAME"]
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
ddb = boto3.client("dynamodb")

# 30-day TTL for JOBLOG records
RECORD_TTL_SECONDS = 30 * 24 * 60 * 60


def handler(event, context):
    # Route SNS lifecycle events vs DynamoDB stream events
    records = event.get("Records", [])
    if records and records[0].get("Sns"):
        return _handle_lifecycle(records)
    return _handle_stream(records)


def _handle_stream(records):
    processed = 0

    for record in records:
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

        # Derive stage from pipeline ID when empty
        if not stage:
            stage = _derive_stage(pipeline_id)

        timestamp = new_image.get("timestamp", {}).get("S", datetime.now(timezone.utc).isoformat())

        logger.info(
            "RUNLOG event: pipeline=%s schedule=%s status=%s stage=%s",
            pipeline_id, schedule_id, status, stage,
        )

        _update_control(pipeline_id, status, timestamp)
        _write_joblog(pipeline_id, schedule_id, stage, status, timestamp)

        # Active chaos recovery on completion
        if status.upper() == "COMPLETED":
            _recover_chaos_events(pipeline_id)

        processed += 1

    return {"statusCode": 200, "processed": processed}


def _handle_lifecycle(records):
    """Handle SNS lifecycle events (PIPELINE_COMPLETED, etc.)."""
    processed = 0

    for record in records:
        message_str = record.get("Sns", {}).get("Message", "{}")
        try:
            message = json.loads(message_str)
        except json.JSONDecodeError:
            logger.warning("skipping lifecycle event with invalid JSON")
            continue

        event_type = message.get("eventType", "")
        pipeline_id = message.get("pipelineId", message.get("pipelineID", ""))

        if not pipeline_id:
            continue

        logger.info("lifecycle event: type=%s pipeline=%s", event_type, pipeline_id)

        if event_type == "PIPELINE_COMPLETED":
            _recover_chaos_events(pipeline_id)

        processed += 1

    return {"statusCode": 200, "processed": processed}


def _derive_stage(pipeline_id):
    """Derive stage from pipeline ID suffix when not provided in RUNLOG data."""
    if "-silver" in pipeline_id:
        return "silver"
    if "-gold" in pipeline_id:
        return "gold"
    return "unknown"


def _recover_chaos_events(pipeline_id):
    """Resolve INJECTED/DETECTED chaos events targeting this pipeline."""
    now = datetime.now(timezone.utc)
    try:
        resp = ddb.query(
            TableName=TABLE_NAME,
            KeyConditionExpression="PK = :pk",
            FilterExpression="#s IN (:s1, :s2) AND target = :tgt",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":pk": {"S": "CHAOS#EVENTS"},
                ":s1": {"S": "INJECTED"},
                ":s2": {"S": "DETECTED"},
                ":tgt": {"S": pipeline_id},
            },
            ScanIndexForward=False,
            Limit=50,
        )
        for item in resp.get("Items", []):
            pk = item["PK"]["S"]
            sk = item["SK"]["S"]
            scenario = item.get("scenario", {}).get("S", "unknown")
            try:
                ddb.update_item(
                    TableName=TABLE_NAME,
                    Key={"PK": {"S": pk}, "SK": {"S": sk}},
                    UpdateExpression="SET #s = :recovered, recoveredAt = :ts",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":recovered": {"S": "RECOVERED"},
                        ":ts": {"S": now.isoformat()},
                    },
                )
                logger.info("recovered chaos event %s for %s", scenario, pipeline_id)
            except ClientError:
                logger.exception("failed to recover chaos event %s for %s", scenario, pipeline_id)
    except ClientError:
        logger.exception("failed to query chaos events for %s", pipeline_id)


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
        elif status_upper == "RUNNING":
            table.update_item(
                Key=key,
                UpdateExpression="SET lastStatus = :st",
                ExpressionAttributeValues={":st": status_upper},
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
