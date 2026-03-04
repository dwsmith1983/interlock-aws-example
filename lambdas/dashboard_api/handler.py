"""Dashboard API Lambda handler.

Serves the interlock observability dashboard via API Gateway v2 (HTTP API).
Reads from a DynamoDB events table that stores pipeline observability events.
"""

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

TABLE_NAME = os.environ.get("EVENTS_TABLE", "interlock-events")
_dynamodb = boto3.resource("dynamodb")
TABLE = _dynamodb.Table(TABLE_NAME)

ONE_HOUR_MS = 3_600_000
ONE_DAY_MS = 86_400_000
SEVEN_DAYS_MS = 7 * ONE_DAY_MS

SLA_TYPES = {"SLA_MET", "SLA_WARNING", "SLA_BREACH"}

# Regex for /api/pipelines/{id}/events
_PIPELINE_EVENTS_RE = re.compile(r"^/api/pipelines/([^/]+)/events$")


def _scan_all(table, **kwargs):
    """Paginate through all scan results."""
    items = []
    while True:
        result = table.scan(**kwargs)
        items.extend(result.get("Items", []))
        if "LastEvaluatedKey" not in result:
            break
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    return items


def _query_all(table, **kwargs):
    """Paginate through all query results."""
    items = []
    while True:
        result = table.query(**kwargs)
        items.extend(result.get("Items", []))
        if "LastEvaluatedKey" not in result:
            break
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    return items


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal values from DynamoDB."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def _now_ms():
    """Current UTC time in milliseconds."""
    return int(time.time() * 1000)


def _response(status_code, body):
    """Build API Gateway v2 response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def _get_qs(event, key, default=None):
    """Safely get a query string parameter."""
    qs = event.get("queryStringParameters") or {}
    return qs.get(key, default)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


def _handle_overview(event):
    """GET /api/overview — last 24h events grouped by pipeline."""
    cutoff = _now_ms() - ONE_DAY_MS

    items = _scan_all(
        TABLE,
        FilterExpression=Attr("timestamp").gte(Decimal(str(cutoff))),
    )

    # Group by pipeline
    by_pipeline = defaultdict(list)
    for item in items:
        pid = item.get("pipelineId", "unknown")
        by_pipeline[pid].append(item)

    pipelines = {}
    for pid, events in sorted(by_pipeline.items()):
        # Sort events by timestamp
        events.sort(key=lambda e: int(e.get("timestamp", 0)))
        types_breakdown = defaultdict(int)
        for e in events:
            et = e.get("eventType", "UNKNOWN")
            types_breakdown[et] += 1

        # Hourly event counts (index 0 = 00:00 UTC, index 23 = 23:00 UTC)
        hourly = [0] * 24
        for e in events:
            ts = e.get("timestamp", 0)
            if isinstance(ts, (int, float, Decimal)) and ts > 0:
                hour = int((int(ts) / 1000) % 86400 // 3600)
                hourly[hour] += 1

        last = events[-1]
        pipelines[pid] = {
            "events": len(events),
            "lastEvent": {
                "eventType": last.get("eventType"),
                "timestamp": last.get("timestamp"),
                "message": last.get("message", ""),
            },
            "types": dict(types_breakdown),
            "recentCounts": hourly,
        }

    return _response(200, {"pipelines": pipelines})


def _handle_pipeline_events(event, pipeline_id):
    """GET /api/pipelines/{id}/events?date=YYYY-MM-DD&hour=HH"""
    date_str = _get_qs(event, "date")
    if not date_str:
        return _response(400, {"error": "Missing required parameter: date"})

    hour_str = _get_qs(event, "hour")

    # Calculate SK range from date (and optional hour)
    try:
        day_start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return _response(400, {"error": "Invalid date format. Expected YYYY-MM-DD"})

    if hour_str is not None:
        try:
            hour = int(hour_str)
            range_start = day_start + timedelta(hours=hour)
            range_end = range_start + timedelta(hours=1)
        except ValueError:
            return _response(400, {"error": "Invalid hour format. Expected 0-23"})
    else:
        range_start = day_start
        range_end = day_start + timedelta(days=1)

    start_ms = str(int(range_start.timestamp() * 1000))
    end_ms = str(int(range_end.timestamp() * 1000))

    items = _query_all(
        TABLE,
        KeyConditionExpression=Key("PK").eq(f"PIPELINE#{pipeline_id}")
        & Key("SK").between(start_ms, end_ms),
    )

    events = [
        {
            "pipelineId": item.get("pipelineId", ""),
            "eventType": item.get("eventType", ""),
            "timestamp": item.get("timestamp", 0),
            "message": item.get("message", ""),
            "date": item.get("date", ""),
            "scheduleId": item.get("scheduleId", ""),
        }
        for item in items
    ]

    return _response(
        200,
        {
            "pipelineId": pipeline_id,
            "date": date_str,
            "events": events,
        },
    )


def _handle_events(event):
    """GET /api/events?type=EVENT_TYPE&from=ts&to=ts"""
    event_type = _get_qs(event, "type")
    now = _now_ms()

    from_ts = _get_qs(event, "from")
    to_ts = _get_qs(event, "to")

    from_val = int(from_ts) if from_ts else now - ONE_DAY_MS
    to_val = int(to_ts) if to_ts else now

    if event_type:
        # Query GSI1 (eventType + timestamp)
        items = _query_all(
            TABLE,
            IndexName="GSI1",
            KeyConditionExpression=Key("eventType").eq(event_type)
            & Key("timestamp").between(Decimal(str(from_val)), Decimal(str(to_val))),
        )
    else:
        # Scan with timestamp filter
        items = _scan_all(
            TABLE,
            FilterExpression=Attr("timestamp").between(
                Decimal(str(from_val)), Decimal(str(to_val))
            ),
        )
    events = [
        {
            "pipelineId": item.get("pipelineId", ""),
            "eventType": item.get("eventType", ""),
            "timestamp": item.get("timestamp", 0),
            "message": item.get("message", ""),
            "date": item.get("date", ""),
            "scheduleId": item.get("scheduleId", ""),
        }
        for item in items
    ]
    return _response(200, {"events": events})


def _handle_metrics(event):
    """GET /api/metrics?from=ts&to=ts — aggregate event statistics."""
    now = _now_ms()

    from_ts = _get_qs(event, "from")
    to_ts = _get_qs(event, "to")

    from_val = int(from_ts) if from_ts else now - SEVEN_DAYS_MS
    to_val = int(to_ts) if to_ts else now

    items = _scan_all(
        TABLE,
        FilterExpression=Attr("timestamp").between(
            Decimal(str(from_val)), Decimal(str(to_val))
        ),
    )

    by_type = defaultdict(int)
    by_pipeline = defaultdict(int)
    by_hour = defaultdict(int)
    sla = {"SLA_MET": 0, "SLA_WARNING": 0, "SLA_BREACH": 0}

    for item in items:
        et = item.get("eventType", "UNKNOWN")
        pid = item.get("pipelineId", "unknown")
        ts = int(item.get("timestamp", 0))

        by_type[et] += 1
        by_pipeline[pid] += 1

        # Bucket by hour
        hour_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        hour_key = hour_dt.strftime("%Y-%m-%dT%H:00Z")
        by_hour[hour_key] += 1

        # SLA tracking
        if et in SLA_TYPES:
            sla[et] += 1

    # Sort byHour
    sorted_by_hour = dict(sorted(by_hour.items()))

    return _response(
        200,
        {
            "totalEvents": len(items),
            "byType": dict(by_type),
            "byPipeline": dict(by_pipeline),
            "byHour": sorted_by_hour,
            "sla": sla,
        },
    )


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------


def handler(event, context):
    """Lambda handler — routes API Gateway v2 HTTP API events."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")

    # OPTIONS preflight
    if method == "OPTIONS":
        return _response(200, {})

    # Route matching
    if path == "/api/overview":
        return _handle_overview(event)

    m = _PIPELINE_EVENTS_RE.match(path)
    if m:
        return _handle_pipeline_events(event, m.group(1))

    if path == "/api/events":
        return _handle_events(event)

    if path == "/api/metrics":
        return _handle_metrics(event)

    return _response(404, {"error": f"Not found: {path}"})
