"""Dry run demo — simulates weather station data arriving throughout each hour.

Each invocation (every 10 min via EventBridge) generates a variable batch of
weather readings, writes them to S3, and updates two cumulative sensors in the
interlock control table:

  weather-ready  — trigger sensor: tracks total/valid readings + completeness
  weather-audit  — post-run sensor: tracks total readings for drift detection
"""

import json
import logging
import os
import random
from datetime import datetime, timezone

import boto3
import botocore.exceptions

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_dynamodb = boto3.client("dynamodb")
_s3 = boto3.client("s3")

_CONTROL_TABLE = os.environ["INTERLOCK_CONTROL_TABLE"]
_S3_BUCKET = os.environ["S3_BUCKET"]

_PIPELINE_ID = "dryrun-weather"
_STATION_IDS = [f"WX-{i:03d}" for i in range(1, 11)]

# Batch size distributions by time-of-day
_DAY_WEIGHTS = [5, 10, 30, 30, 15, 10]    # sizes 1-6, mean ~3.7
_NIGHT_WEIGHTS = [25, 30, 25, 15, 4, 1]   # sizes 1-6, mean ~2.2

_TRIGGER_THRESHOLD = 12
_VALID_PCT_THRESHOLD = 0.75
_QUALITY_MIN = 0.5
_QUALITY_MAX = 1.0
_DEGRADED_THRESHOLD = 0.7
_GOOD_QUALITY_PROBABILITY = 0.85


def handler(event: dict, context: object) -> dict:
    """Generate weather readings and update interlock sensors."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")
    hour_int = now.hour

    readings = _generate_readings(hour_int, now_iso)
    _write_to_s3(readings, par_day, par_hour, context)

    valid_count = sum(1 for r in readings if r["quality"] >= _DEGRADED_THRESHOLD)
    total_count = len(readings)

    sensor_suffix = f"#{par_day}T{par_hour}"

    _update_trigger_sensor(sensor_suffix, par_day, par_hour, total_count, valid_count, now_iso)
    _update_audit_sensor(sensor_suffix, par_day, par_hour, total_count, now_iso)

    logger.info(
        "dryrun-weather %sT%s: wrote %d readings (%d valid) to S3 and sensors",
        par_day,
        par_hour,
        total_count,
        valid_count,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "par_day": par_day,
            "par_hour": par_hour,
            "total_readings": total_count,
            "valid_readings": valid_count,
        }),
    }


def _generate_readings(hour: int, timestamp: str) -> list[dict]:
    """Generate a batch of weather readings with time-of-day weighted size."""
    weights = _NIGHT_WEIGHTS if hour < 6 else _DAY_WEIGHTS
    batch_size = random.choices(range(1, 7), weights=weights, k=1)[0]

    readings = []
    for _ in range(batch_size):
        if random.random() < _GOOD_QUALITY_PROBABILITY:
            quality = round(random.uniform(_DEGRADED_THRESHOLD, _QUALITY_MAX), 3)
        else:
            quality = round(random.uniform(_QUALITY_MIN, _DEGRADED_THRESHOLD), 3)

        readings.append({
            "station_id": random.choice(_STATION_IDS),
            "temperature_c": round(random.uniform(5.0, 40.0), 1),
            "humidity_pct": round(random.uniform(20.0, 95.0), 1),
            "quality": quality,
            "timestamp": timestamp,
        })

    return readings


def _write_to_s3(
    readings: list[dict], par_day: str, par_hour: str, context: object,
) -> None:
    """Write readings batch to S3 as JSON.

    Uses the Lambda request ID as the S3 key suffix for idempotency —
    retries of the same invocation overwrite the same object.
    """
    request_id = getattr(context, "aws_request_id", None) or "local"
    key = f"dryrun-demo/par_day={par_day}/par_hour={par_hour}/{request_id}.json"
    _s3.put_object(
        Bucket=_S3_BUCKET,
        Key=key,
        Body=json.dumps(readings, default=str),
        ContentType="application/json",
    )


def _ensure_data_map(key: dict) -> None:
    """Ensure the nested data map exists on the sensor record."""
    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression="SET #data = if_not_exists(#data, :empty_map)",
        ExpressionAttributeNames={"#data": "data"},
        ExpressionAttributeValues={":empty_map": {"M": {}}},
    )


def _update_trigger_sensor(
    sensor_suffix: str,
    par_day: str,
    par_hour: str,
    total_count: int,
    valid_count: int,
    now_iso: str,
) -> None:
    """Update weather-ready sensor with atomic increments.

    Sets complete=true when total_readings >= 12 AND valid_pct >= 0.75.
    Uses ConditionExpression to guard against concurrent complete writes.
    """
    key = {
        "PK": {"S": f"PIPELINE#{_PIPELINE_ID}"},
        "SK": {"S": f"SENSOR#weather-ready{sensor_suffix}"},
    }

    _ensure_data_map(key)

    resp = _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression=(
            "SET #data.#date = :date, #data.#hour = :hour, #data.updatedAt = :now "
            "ADD #data.total_readings :total, #data.valid_readings :valid, "
            "#data.batches_received :one"
        ),
        ExpressionAttributeNames={
            "#data": "data",
            "#date": "date",
            "#hour": "hour",
        },
        ExpressionAttributeValues={
            ":date": {"S": par_day},
            ":hour": {"S": par_hour},
            ":now": {"S": now_iso},
            ":total": {"N": str(total_count)},
            ":valid": {"N": str(valid_count)},
            ":one": {"N": "1"},
        },
        ReturnValues="ALL_NEW",
    )

    attrs = resp.get("Attributes", {})
    data = attrs.get("data", {}).get("M", {})
    cumulative_total = int(data.get("total_readings", {}).get("N", "0"))
    cumulative_valid = int(data.get("valid_readings", {}).get("N", "0"))

    valid_pct = cumulative_valid / cumulative_total if cumulative_total > 0 else 0.0

    if cumulative_total >= _TRIGGER_THRESHOLD and valid_pct >= _VALID_PCT_THRESHOLD:
        try:
            _dynamodb.update_item(
                TableName=_CONTROL_TABLE,
                Key=key,
                UpdateExpression="SET #data.#complete = :complete",
                ConditionExpression="attribute_not_exists(#data.#complete)",
                ExpressionAttributeNames={"#data": "data", "#complete": "complete"},
                ExpressionAttributeValues={":complete": {"BOOL": True}},
            )
            logger.info(
                "weather-ready %s: COMPLETE — %d readings, %.1f%% valid",
                sensor_suffix,
                cumulative_total,
                valid_pct * 100,
            )
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "weather-ready %s: complete already set by concurrent invocation",
                    sensor_suffix,
                )
            else:
                raise
    else:
        logger.info(
            "weather-ready %s: %d/%d readings, %.1f%% valid",
            sensor_suffix,
            cumulative_total,
            _TRIGGER_THRESHOLD,
            valid_pct * 100,
        )


def _update_audit_sensor(
    sensor_suffix: str,
    par_day: str,
    par_hour: str,
    total_count: int,
    now_iso: str,
) -> None:
    """Update weather-audit sensor for post-run drift detection.

    Write-only — no need to read back cumulative values.
    """
    key = {
        "PK": {"S": f"PIPELINE#{_PIPELINE_ID}"},
        "SK": {"S": f"SENSOR#weather-audit{sensor_suffix}"},
    }

    _ensure_data_map(key)

    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression=(
            "SET #data.#date = :date, #data.#hour = :hour, #data.updatedAt = :now "
            "ADD #data.total_readings :total"
        ),
        ExpressionAttributeNames={
            "#data": "data",
            "#date": "date",
            "#hour": "hour",
        },
        ExpressionAttributeValues={
            ":date": {"S": par_day},
            ":hour": {"S": par_hour},
            ":now": {"S": now_iso},
            ":total": {"N": str(total_count)},
        },
    )
