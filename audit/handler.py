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
    """Audit bronze data for the previous hour.

    Reads the bronze Delta table partition, counts records,
    compares to sensor count, writes audit-result sensor.
    """
    now = datetime.now(timezone.utc)
    # Audit runs at :10 past the hour for the PREVIOUS hour
    target = now - timedelta(hours=1)
    par_day = target.strftime("%Y%m%d")
    par_hour = f"{target.hour:02d}"

    results = {}
    for stream in ("cdr", "seq"):
        pipeline_id = f"bronze-{stream}"

        # Read sensor count
        sensor_resp = _dynamodb.get_item(
            TableName=_CONTROL_TABLE,
            Key={
                "PK": {"S": f"PIPELINE#{pipeline_id}"},
                "SK": {"S": "SENSOR#hourly-status"},
            },
        )
        sensor_data = sensor_resp.get("Item", {}).get("data", {}).get("M", {})
        sensor_count = int(sensor_data.get("count", {}).get("N", "0"))
        sensor_date = sensor_data.get("date", {}).get("S", "")
        sensor_hour = sensor_data.get("hour", {}).get("S", "")

        # Verify sensor is for the correct partition
        if sensor_date != par_day or sensor_hour != par_hour:
            logger.warning(
                "%s sensor date/hour mismatch: sensor=%s/%s, expected=%s/%s",
                stream, sensor_date, sensor_hour, par_day, par_hour,
            )
            results[stream] = {"match": False, "reason": "sensor_stale"}
            continue

        # Count records in Delta table partition
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

        # Write audit-result sensor
        audit_now = datetime.now(timezone.utc).isoformat()
        _dynamodb.put_item(
            TableName=_CONTROL_TABLE,
            Item={
                "PK": {"S": f"PIPELINE#{pipeline_id}"},
                "SK": {"S": "SENSOR#audit-result"},
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
