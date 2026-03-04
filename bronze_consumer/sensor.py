"""Sensor writer for Interlock control table."""
import logging
import math
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

_dynamodb = boto3.client("dynamodb")
_CONTROL_TABLE = os.environ.get("INTERLOCK_CONTROL_TABLE", "")
_CDR_DAILY_TARGET = int(os.environ.get("CDR_DAILY_TARGET", "100000000"))
_SEQ_DAILY_TARGET = int(os.environ.get("SEQ_DAILY_TARGET", "500000000"))


def _traffic_weight(hour: float) -> float:
    """Bimodal traffic distribution matching generator/distribution.py."""
    return (
        0.10
        + 0.70 * math.exp(-((hour - 10) ** 2) / 18)
        + 0.50 * math.exp(-((hour - 20) ** 2) / 12.5)
    )


def _expected_hourly_count(daily_target: int, hour: int) -> int:
    """Compute expected record count for a given hour using traffic distribution."""
    total_weight = sum(
        _traffic_weight(i * 0.25 + 7.5 / 60.0) for i in range(96)
    )
    hour_weight = sum(
        _traffic_weight(hour + (m + 7.5) / 60.0) for m in [0, 15, 30, 45]
    )
    return round(daily_target * hour_weight / total_weight)


def update_hourly_sensor(
    stream: str,
    par_day: str,
    par_hour: str,
    record_count: int,
) -> None:
    """Update the hourly-status sensor in Interlock control table.

    Sensor fields are stored inside a "data" map attribute to match the
    framework's canonical ControlRecord format. The stream-router unwraps
    this map when evaluating trigger conditions.

    Uses DynamoDB UpdateItem with ADD to atomically increment count and files_processed.
    Sets complete=true when pct_of_expected >= 0.7 (matching the validation rule).
    Each time period gets its own sensor record (keyed by date+hour).
    """
    if not _CONTROL_TABLE:
        logger.warning("INTERLOCK_CONTROL_TABLE not set, skipping sensor write")
        return

    pipeline_id = f"bronze-{stream}"
    daily_target = _CDR_DAILY_TARGET if stream == "cdr" else _SEQ_DAILY_TARGET
    hour_int = int(par_hour)
    expected = _expected_hourly_count(daily_target, hour_int)

    now = datetime.now(timezone.utc).isoformat()
    sensor_suffix = f"#{par_day}T{par_hour}"
    key = {
        "PK": {"S": f"PIPELINE#{pipeline_id}"},
        "SK": {"S": f"SENSOR#hourly-status{sensor_suffix}"},
    }

    # Ensure the data map exists (no-op if it already does)
    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression="SET #data = if_not_exists(#data, :empty_map)",
        ExpressionAttributeNames={"#data": "data"},
        ExpressionAttributeValues={":empty_map": {"M": {}}},
    )

    # Atomic increment of count and files_processed inside the data map
    resp = _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression=(
            "SET #data.#date = :date, #data.#hour = :hour, "
            "#data.expected_count = :expected, #data.updatedAt = :now "
            "ADD #data.#count :count, #data.files_processed :one"
        ),
        ExpressionAttributeNames={
            "#data": "data",
            "#date": "date",
            "#hour": "hour",
            "#count": "count",
        },
        ExpressionAttributeValues={
            ":date": {"S": par_day},
            ":hour": {"S": par_hour},
            ":expected": {"N": str(expected)},
            ":now": {"S": now},
            ":count": {"N": str(record_count)},
            ":one": {"N": "1"},
        },
        ReturnValues="ALL_NEW",
    )

    # Read back values from the data map
    attrs = resp.get("Attributes", {})
    data = attrs.get("data", {}).get("M", {})
    files_processed = int(data.get("files_processed", {}).get("N", "0"))
    total_count = int(data.get("count", {}).get("N", "0"))

    pct = total_count / expected if expected > 0 else 0.0
    if files_processed >= 4 and pct >= 0.7:
        _dynamodb.update_item(
            TableName=_CONTROL_TABLE,
            Key=key,
            UpdateExpression=(
                "SET #data.complete = :complete, #data.pct_of_expected = :pct"
            ),
            ExpressionAttributeNames={"#data": "data"},
            ExpressionAttributeValues={
                ":complete": {"BOOL": True},
                ":pct": {"N": f"{pct:.4f}"},
            },
        )
        logger.info(
            "Bronze %s hour %s complete: %d records (%.1f%% of expected %d)",
            stream, par_hour, total_count, pct * 100, expected,
        )
        # Propagate sensor to silver hourly pipeline so stream-router
        # sees it on the silver PK and triggers SFN execution.
        silver_key = {
            "PK": {"S": f"PIPELINE#silver-{stream}-hour"},
            "SK": {"S": f"SENSOR#hourly-status{sensor_suffix}"},
        }
        _dynamodb.put_item(
            TableName=_CONTROL_TABLE,
            Item={
                **silver_key,
                "data": {"M": {
                    "date": {"S": par_day},
                    "hour": {"S": par_hour},
                    "count": {"N": str(total_count)},
                    "expected_count": {"N": str(expected)},
                    "files_processed": {"N": str(files_processed)},
                    "complete": {"BOOL": True},
                    "pct_of_expected": {"N": f"{pct:.4f}"},
                    "updatedAt": {"S": now},
                }},
            },
        )
        logger.info("Propagated sensor to silver-%s-hour", stream)

        # Update daily-status sensor for silver daily pipeline.
        # Track completed hours in a StringSet; when all 24 arrive,
        # set all_hours_complete=true which triggers the daily SFN.
        _update_daily_sensor(stream, par_day, par_hour, now)
    else:
        logger.info(
            "Bronze %s hour %s: %d/%d files, %d records so far",
            stream, par_hour, files_processed, 48, total_count,
        )


def _update_daily_sensor(stream: str, par_day: str, par_hour: str, now: str) -> None:
    """Update daily-status sensor on the silver daily pipeline PK.

    Each day gets its own sensor record (keyed by date). Adds the completed
    hour to a StringSet. When all 24 hours are present, sets
    all_hours_complete=true. This write triggers the stream-router to start
    the daily SFN.
    """
    daily_key = {
        "PK": {"S": f"PIPELINE#silver-{stream}-day"},
        "SK": {"S": f"SENSOR#daily-status#{par_day}"},
    }

    # Ensure data map exists
    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=daily_key,
        UpdateExpression="SET #data = if_not_exists(#data, :empty_map)",
        ExpressionAttributeNames={"#data": "data"},
        ExpressionAttributeValues={":empty_map": {"M": {}}},
    )

    # Add hour to completed set and update metadata
    resp = _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=daily_key,
        UpdateExpression=(
            "SET #data.#date = :date, #data.updatedAt = :now "
            "ADD #data.completed_hours :hour_set"
        ),
        ExpressionAttributeNames={
            "#data": "data",
            "#date": "date",
        },
        ExpressionAttributeValues={
            ":date": {"S": par_day},
            ":now": {"S": now},
            ":hour_set": {"SS": [par_hour]},
        },
        ReturnValues="ALL_NEW",
    )

    # Check if all 24 hours are complete
    attrs = resp.get("Attributes", {})
    data = attrs.get("data", {}).get("M", {})
    completed = data.get("completed_hours", {}).get("SS", [])

    if len(completed) >= 24:
        _dynamodb.update_item(
            TableName=_CONTROL_TABLE,
            Key=daily_key,
            UpdateExpression="SET #data.all_hours_complete = :complete",
            ExpressionAttributeNames={"#data": "data"},
            ExpressionAttributeValues={":complete": {"BOOL": True}},
        )
        logger.info(
            "Silver %s day %s: all 24 hours complete, daily pipeline triggered",
            stream, par_day,
        )
    else:
        logger.info(
            "Silver %s day %s: %d/24 hours complete",
            stream, par_day, len(completed),
        )
