"""SNS alert logger — persists alerts to CloudWatch Logs, DynamoDB ALERT# and ERROR# records,
and updates CONTROL# pipeline health status."""

import json
import logging
import os
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

# 30-day TTL for alert/error records
RECORD_TTL_SECONDS = 30 * 24 * 60 * 60


def handler(event, context):
    for record in event.get("Records", []):
        message_str = record.get("Sns", {}).get("Message", "{}")
        timestamp = record.get("Sns", {}).get("Timestamp", "")

        try:
            alert = json.loads(message_str)
        except json.JSONDecodeError:
            alert = {"raw": message_str}

        pipeline_id = alert.get("pipelineId", alert.get("pipelineID", "unknown"))
        details = alert.get("details", {})
        schedule_id = details.get("scheduleId", alert.get("scheduleID", ""))
        alert_type = details.get("type", alert.get("type", "unknown"))
        severity = alert.get("level", alert.get("severity", "warning"))

        # Structured log line
        log_entry = {
            "alert": True,
            "pipelineID": pipeline_id,
            "scheduleID": schedule_id,
            "type": alert_type,
            "severity": severity,
            "timestamp": timestamp,
            "detail": alert,
        }
        logger.info(json.dumps(log_entry))

        now = int(time.time())

        # Persist ALERT# record
        sk = f"ALERT#{timestamp}#{alert_type}"
        if schedule_id:
            sk = f"ALERT#{timestamp}#{schedule_id}#{alert_type}"

        table.put_item(
            Item={
                "PK": f"PIPELINE#{pipeline_id}",
                "SK": sk,
                "GSI1PK": "ALERTS",
                "GSI1SK": f"{timestamp}#{pipeline_id}",
                "data": json.dumps(alert),
                "alertType": alert_type,
                "severity": severity,
                "scheduleID": schedule_id,
                "timestamp": timestamp,
                "ttl": now + RECORD_TTL_SECONDS,
            }
        )

        # Write ERROR# record for failures
        if alert_type in ("error", "sla_breach", "evaluation_failure", "trigger_failure", "unknown"):
            error_sk = f"{timestamp}#{alert_type}"
            table.put_item(
                Item={
                    "PK": f"ERROR#{pipeline_id}",
                    "SK": error_sk,
                    "GSI1PK": "ERRORS",
                    "GSI1SK": f"{timestamp}#{pipeline_id}",
                    "errorType": alert_type,
                    "scheduleID": schedule_id,
                    "message": json.dumps(details),
                    "resolved": False,
                    "timestamp": timestamp,
                    "ttl": now + RECORD_TTL_SECONDS,
                }
            )

        # Update CONTROL# pipeline health
        _update_control(pipeline_id, alert_type, timestamp)

    return {"statusCode": 200, "processed": len(event.get("Records", []))}


def _update_control(pipeline_id, alert_type, timestamp):
    """Update CONTROL# record with failure info."""
    try:
        table.update_item(
            Key={
                "PK": f"CONTROL#{pipeline_id}",
                "SK": "STATUS",
            },
            UpdateExpression="SET lastFailedRun = :ts, lastAlertType = :at ADD consecutiveFailures :one",
            ExpressionAttributeValues={
                ":ts": timestamp,
                ":at": alert_type,
                ":one": 1,
            },
        )
    except Exception:
        logger.exception("failed to update CONTROL record for %s", pipeline_id)
