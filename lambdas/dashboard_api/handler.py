"""Dashboard API: Read-only queries against DynamoDB observability records.

Serves GET /dashboard/* routes via API Gateway HTTP API (payload format 2.0).
Routes:
  /dashboard/overview          - Summary of all pipelines + recent chaos + alerts
  /dashboard/pipelines         - List all pipeline configs
  /dashboard/pipelines/{id}/status  - Current health for one pipeline
  /dashboard/pipelines/{id}/jobs    - Recent job history
  /dashboard/pipelines/{id}/runlogs - Recent run log entries
  /dashboard/chaos/events      - All chaos injection events
  /dashboard/chaos/config      - Current chaos configuration
  /dashboard/alerts            - Recent alerts (last 50)
"""

import json
import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("TABLE_NAME", "medallion-interlock")
ddb = boto3.client("dynamodb")

PIPELINES = ["earthquake-silver", "earthquake-gold", "crypto-silver", "crypto-gold"]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}

# Route pattern: /dashboard/pipelines/{id}/status etc.
PIPELINE_RE = re.compile(r"^/dashboard/pipelines/([^/]+)/(\w+)$")


def handler(event, context):
    """Main entry point for API Gateway HTTP API (format 2.0)."""
    path = event.get("rawPath", "")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    # Handle CORS preflight
    if method == "OPTIONS":
        return _response(200, {"message": "ok"})

    logger.info("dashboard-api: %s %s", method, path)

    try:
        if path == "/dashboard/overview":
            return _handle_overview()
        elif path == "/dashboard/pipelines":
            return _handle_pipelines()
        elif path == "/dashboard/chaos/events":
            return _handle_chaos_events()
        elif path == "/dashboard/chaos/config":
            return _handle_chaos_config()
        elif path == "/dashboard/alerts":
            return _handle_alerts()
        else:
            # Check for /dashboard/pipelines/{id}/{action}
            m = PIPELINE_RE.match(path)
            if m:
                pipeline_id = m.group(1)
                action = m.group(2)
                if action == "status":
                    return _handle_pipeline_status(pipeline_id)
                elif action == "jobs":
                    return _handle_pipeline_jobs(pipeline_id)
                elif action == "runlogs":
                    return _handle_pipeline_runlogs(pipeline_id)

        return _response(404, {"error": "not found", "path": path})

    except Exception:
        logger.exception("unhandled error for %s", path)
        return _response(500, {"error": "internal server error"})


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_overview():
    """Dashboard summary: all pipeline statuses + recent chaos + recent alerts."""
    # Query all CONTROL# records
    pipeline_statuses = []
    for pid in PIPELINES:
        status = _get_pipeline_status(pid)
        if status:
            pipeline_statuses.append(status)

    # Recent chaos events (last 20)
    chaos_events = _query_items(
        pk="CHAOS#EVENTS",
        limit=20,
        scan_forward=False,
    )

    # Recent alerts (last 10 via GSI1)
    alerts = _query_gsi1(
        gsi1pk="ALERTS",
        limit=10,
        scan_forward=False,
    )

    # Chaos config summary
    chaos_config = _get_chaos_config()

    return _response(200, {
        "pipelines": pipeline_statuses,
        "chaosEvents": [_unmarshall(e) for e in chaos_events],
        "recentAlerts": [_unmarshall(a) for a in alerts],
        "chaosConfig": chaos_config,
    })


def _handle_pipelines():
    """List all pipeline configs via GSI1PK=TYPE#pipeline."""
    items = _query_gsi1(
        gsi1pk="TYPE#pipeline",
        limit=50,
    )

    pipelines = []
    for item in items:
        flat = _unmarshall(item)
        # Parse the embedded JSON config
        if "data" in flat:
            try:
                flat["config"] = json.loads(flat["data"])
                del flat["data"]
            except (json.JSONDecodeError, TypeError):
                pass
        pipelines.append(flat)

    return _response(200, {"pipelines": pipelines})


def _handle_pipeline_status(pipeline_id):
    """Current health for one pipeline from CONTROL#{id} STATUS."""
    status = _get_pipeline_status(pipeline_id)
    if not status:
        return _response(404, {"error": f"pipeline {pipeline_id} not found"})
    return _response(200, status)


def _handle_pipeline_jobs(pipeline_id):
    """Recent job history from JOBLOG#{id}."""
    items = _query_items(
        pk=f"JOBLOG#{pipeline_id}",
        limit=50,
        scan_forward=False,
    )
    return _response(200, {
        "pipelineId": pipeline_id,
        "jobs": [_unmarshall(i) for i in items],
    })


def _handle_pipeline_runlogs(pipeline_id):
    """Run log entries from PIPELINE#{id} where SK begins_with RUNLOG#."""
    items = _query_items(
        pk=f"PIPELINE#{pipeline_id}",
        sk_prefix="RUNLOG#",
        limit=50,
        scan_forward=False,
    )

    runlogs = []
    for item in items:
        flat = _unmarshall(item)
        if "data" in flat:
            try:
                flat["runData"] = json.loads(flat["data"])
                del flat["data"]
            except (json.JSONDecodeError, TypeError):
                pass
        runlogs.append(flat)

    return _response(200, {
        "pipelineId": pipeline_id,
        "runlogs": runlogs,
    })


def _handle_chaos_events():
    """All chaos injection events from PK=CHAOS#EVENTS."""
    items = _query_items(
        pk="CHAOS#EVENTS",
        limit=100,
        scan_forward=False,
    )
    return _response(200, {
        "events": [_unmarshall(i) for i in items],
    })


def _handle_chaos_config():
    """Current chaos configuration from CHAOS#CONFIG CURRENT."""
    config = _get_chaos_config()
    return _response(200, config)


def _handle_alerts():
    """Recent alerts via GSI1PK=ALERTS, limit 50."""
    items = _query_gsi1(
        gsi1pk="ALERTS",
        limit=50,
        scan_forward=False,
    )

    alerts = []
    for item in items:
        flat = _unmarshall(item)
        if "data" in flat:
            try:
                flat["alertData"] = json.loads(flat["data"])
                del flat["data"]
            except (json.JSONDecodeError, TypeError):
                pass
        alerts.append(flat)

    return _response(200, {"alerts": alerts})


# ---------------------------------------------------------------------------
# DynamoDB query helpers
# ---------------------------------------------------------------------------

def _get_pipeline_status(pipeline_id):
    """Get CONTROL# record for a pipeline."""
    try:
        resp = ddb.get_item(
            TableName=TABLE_NAME,
            Key={
                "PK": {"S": f"CONTROL#{pipeline_id}"},
                "SK": {"S": "STATUS"},
            },
        )
        item = resp.get("Item")
        if not item:
            return None
        flat = _unmarshall(item)
        flat["pipelineId"] = pipeline_id
        return flat
    except ClientError:
        logger.exception("failed to get CONTROL# for %s", pipeline_id)
        return None


def _get_chaos_config():
    """Get CHAOS#CONFIG CURRENT record."""
    try:
        resp = ddb.get_item(
            TableName=TABLE_NAME,
            Key={
                "PK": {"S": "CHAOS#CONFIG"},
                "SK": {"S": "CURRENT"},
            },
        )
        item = resp.get("Item")
        if not item:
            return {"enabled": False, "scenarios": []}
        flat = _unmarshall(item)
        if "data" in flat:
            try:
                return json.loads(flat["data"])
            except (json.JSONDecodeError, TypeError):
                pass
        return flat
    except ClientError:
        logger.exception("failed to get CHAOS#CONFIG")
        return {"enabled": False, "scenarios": []}


def _query_items(pk, sk_prefix=None, limit=50, scan_forward=True):
    """Query DynamoDB by PK, optionally filtering SK prefix."""
    params = {
        "TableName": TABLE_NAME,
        "ScanIndexForward": scan_forward,
        "Limit": limit,
    }

    if sk_prefix:
        params["KeyConditionExpression"] = "PK = :pk AND begins_with(SK, :skp)"
        params["ExpressionAttributeValues"] = {
            ":pk": {"S": pk},
            ":skp": {"S": sk_prefix},
        }
    else:
        params["KeyConditionExpression"] = "PK = :pk"
        params["ExpressionAttributeValues"] = {
            ":pk": {"S": pk},
        }

    try:
        resp = ddb.query(**params)
        return resp.get("Items", [])
    except ClientError:
        logger.exception("query failed for PK=%s", pk)
        return []


def _query_gsi1(gsi1pk, limit=50, scan_forward=True):
    """Query GSI1 by GSI1PK."""
    try:
        resp = ddb.query(
            TableName=TABLE_NAME,
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={
                ":pk": {"S": gsi1pk},
            },
            ScanIndexForward=scan_forward,
            Limit=limit,
        )
        return resp.get("Items", [])
    except ClientError:
        logger.exception("GSI1 query failed for GSI1PK=%s", gsi1pk)
        return []


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _unmarshall(item):
    """Convert DynamoDB low-level item to a plain dict."""
    result = {}
    for key, value in item.items():
        if "S" in value:
            result[key] = value["S"]
        elif "N" in value:
            n = value["N"]
            result[key] = int(n) if "." not in n else float(n)
        elif "BOOL" in value:
            result[key] = value["BOOL"]
        elif "NULL" in value:
            result[key] = None
        elif "L" in value:
            result[key] = [_unmarshall_value(v) for v in value["L"]]
        elif "M" in value:
            result[key] = _unmarshall(value["M"])
        else:
            result[key] = str(value)
    return result


def _unmarshall_value(value):
    """Unmarshall a single DynamoDB attribute value."""
    if "S" in value:
        return value["S"]
    elif "N" in value:
        n = value["N"]
        return int(n) if "." not in n else float(n)
    elif "BOOL" in value:
        return value["BOOL"]
    elif "NULL" in value:
        return None
    elif "M" in value:
        return _unmarshall(value["M"])
    elif "L" in value:
        return [_unmarshall_value(v) for v in value["L"]]
    return str(value)


def _response(status_code, body):
    """Build API Gateway response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=str),
    }
