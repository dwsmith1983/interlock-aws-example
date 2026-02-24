"""SNS alert logger — persists alerts to CloudWatch Logs and DynamoDB."""

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

# 30-day TTL for alert records
ALERT_TTL_SECONDS = 30 * 24 * 60 * 60


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

        # Persist to DynamoDB
        now = int(time.time())
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
                "ttl": now + ALERT_TTL_SECONDS,
            }
        )

    return {"statusCode": 200, "processed": len(event.get("Records", []))}
