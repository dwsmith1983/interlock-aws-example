"""SNS alert logger — persists alerts to CloudWatch Logs, DynamoDB ALERT# and ERROR# records,
updates CONTROL# pipeline health status, and forwards to Slack."""

import json
import logging
import os
import time
import urllib.request
import urllib.error

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

# 30-day TTL for alert/error records
RECORD_TTL_SECONDS = 30 * 24 * 60 * 60

# Slack severity → color mapping
_SEVERITY_COLORS = {
    "error": "#e01e5a",    # red
    "warning": "#ecb22e",  # yellow
    "info": "#2eb886",     # blue/green
}


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
        # Prefer new Category field (alertType), fall back to details.type, then alert.type
        alert_type = alert.get("alertType", details.get("type", alert.get("type", "unknown")))
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
        if alert_type in (
            "error", "sla_breach", "evaluation_failure", "trigger_failure", "unknown",
            "schedule_missed", "stuck_run", "evaluation_sla_breach",
            "completion_sla_breach", "validation_timeout", "trait_drift",
        ):
            error_sk = f"{timestamp}#{alert_type}"
            table.put_item(
                Item={
                    "PK": f"ERROR#{pipeline_id}",
                    "SK": error_sk,
                    "GSI1PK": "ERRORS",
                    "GSI1SK": f"{timestamp}#{pipeline_id}",
                    "errorType": alert_type,
                    "scheduleID": schedule_id,
                    "message": alert.get("message", ""),
                    "resolved": False,
                    "timestamp": timestamp,
                    "ttl": now + RECORD_TTL_SECONDS,
                }
            )

        # Update CONTROL# pipeline health
        _update_control(pipeline_id, alert_type, timestamp)

        # Forward to Slack
        _notify_slack(pipeline_id, alert_type, severity, schedule_id, timestamp, alert)

    return {"statusCode": 200, "processed": len(event.get("Records", []))}


def _update_control(pipeline_id, alert_type, timestamp):
    """Update CONTROL# record with alert metadata only.

    Pipeline-monitor owns consecutiveFailures via COMPLETED/FAILED RUNLOG events.
    Alert-logger only tracks the latest alert type and timestamp.
    """
    try:
        table.update_item(
            Key={
                "PK": f"CONTROL#{pipeline_id}",
                "SK": "STATUS",
            },
            UpdateExpression="SET lastAlertType = :at, lastAlertAt = :ts",
            ExpressionAttributeValues={
                ":at": alert_type,
                ":ts": timestamp,
            },
        )
    except Exception:
        logger.exception("failed to update CONTROL record for %s", pipeline_id)


def _notify_slack(pipeline_id, alert_type, severity, schedule_id, timestamp, alert):
    """Post alert to Slack webhook. Fails gracefully — logs and continues."""
    if not SLACK_WEBHOOK_URL:
        return

    color = _SEVERITY_COLORS.get(severity, "#808080")
    message = alert.get("message", "")

    payload = {
        "attachments": [
            {
                "color": color,
                "fallback": f"[{severity.upper()}] {pipeline_id}: {alert_type}",
                "fields": [
                    {"title": "Pipeline", "value": pipeline_id, "short": True},
                    {"title": "Alert Type", "value": alert_type, "short": True},
                    {"title": "Severity", "value": severity.upper(), "short": True},
                    {"title": "Schedule", "value": schedule_id or "—", "short": True},
                    {"title": "Timestamp", "value": timestamp, "short": False},
                    {"title": "Message", "value": message or "—", "short": False},
                ],
            }
        ]
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except (urllib.error.URLError, OSError):
        logger.exception("Slack webhook POST failed for %s", pipeline_id)
