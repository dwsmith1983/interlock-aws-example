"""Bronze audit Lambda — reconciles Delta table records against sensor count."""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
from deltalake import DeltaTable

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_dynamodb = boto3.client("dynamodb")
_CONTROL_TABLE = os.environ.get("INTERLOCK_CONTROL_TABLE", "")
_S3_BUCKET = os.environ.get("S3_BUCKET", "")


def lambda_handler(event, context):
    """Audit bronze data for a given hour.

    Reads par_day/par_hour from the request body (injected by the framework)
    or falls back to clock-based calculation for backward compatibility.
    """
    # Parse execution context from request body if available.
    body = {}
    if isinstance(event, dict) and event.get("body"):
        try:
            raw = event["body"]
            body = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            pass

    if "par_day" in body:
        par_day = body["par_day"]
        par_hour = body.get("par_hour", "")
    else:
        # Fallback: calculate from clock (audit runs shortly after the hour).
        now = datetime.now(timezone.utc)
        target = now - timedelta(hours=1)
        par_day = target.strftime("%Y%m%d")
        par_hour = f"{target.hour:02d}"

    # Build per-period sensor key suffix.
    sensor_suffix = f"#{par_day}T{par_hour}" if par_hour else f"#{par_day}"

    results = {}
    for stream in ("cdr", "seq"):
        pipeline_id = f"bronze-{stream}"

        # Read per-period sensor count.
        sensor_resp = _dynamodb.get_item(
            TableName=_CONTROL_TABLE,
            Key={
                "PK": {"S": f"PIPELINE#{pipeline_id}"},
                "SK": {"S": f"SENSOR#hourly-status{sensor_suffix}"},
            },
        )
        sensor_data = sensor_resp.get("Item", {}).get("data", {}).get("M", {})
        sensor_count = int(sensor_data.get("count", {}).get("N", "0"))

        if sensor_count == 0:
            logger.warning("%s: no sensor data found for %s", stream, sensor_suffix)
            results[stream] = {"match": False, "reason": "no_sensor_data"}
            continue

        # Count records in Delta table partition.
        uri = f"s3://{_S3_BUCKET}/bronze/{stream}"
        try:
            dt = DeltaTable(uri)
            ds = dt.to_pyarrow_dataset()
            filtered = ds.filter(
                (ds.field("par_day") == par_day) & (ds.field("par_hour") == par_hour)
            )
            delta_count = filtered.count_rows()
        except Exception:
            logger.exception("Failed to read Delta table for %s", stream)
            delta_count = 0

        match = delta_count == sensor_count
        logger.info(
            "%s audit: sensor=%d, delta=%d, match=%s",
            stream, sensor_count, delta_count, match,
        )

        # Write per-period audit-result sensor.
        audit_now = datetime.now(timezone.utc).isoformat()
        _dynamodb.put_item(
            TableName=_CONTROL_TABLE,
            Item={
                "PK": {"S": f"PIPELINE#{pipeline_id}"},
                "SK": {"S": f"SENSOR#audit-result{sensor_suffix}"},
                "data": {"M": {
                    "date": {"S": par_day},
                    "hour": {"S": par_hour},
                    "sensor_count": {"N": str(sensor_count)},
                    "delta_count": {"N": str(delta_count)},
                    "match": {"BOOL": match},
                    "updatedAt": {"S": audit_now},
                }},
            },
        )
        results[stream] = {"match": match, "sensor": sensor_count, "delta": delta_count}

    return {
        "statusCode": 200,
        "body": json.dumps(results),
    }
