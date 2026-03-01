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
    Sets complete=true when files_processed reaches 4.
    """
    if not _CONTROL_TABLE:
        logger.warning("INTERLOCK_CONTROL_TABLE not set, skipping sensor write")
        return

    pipeline_id = f"bronze-{stream}"
    daily_target = _CDR_DAILY_TARGET if stream == "cdr" else _SEQ_DAILY_TARGET
    hour_int = int(par_hour)
    expected = _expected_hourly_count(daily_target, hour_int)

    now = datetime.now(timezone.utc).isoformat()
    key = {
        "PK": {"S": f"PIPELINE#{pipeline_id}"},
        "SK": {"S": "SENSOR#hourly-status"},
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

    if files_processed >= 4:
        pct = total_count / expected if expected > 0 else 0.0
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
            "SK": {"S": "SENSOR#hourly-status"},
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
    else:
        logger.info(
            "Bronze %s hour %s: %d/%d files, %d records so far",
            stream, par_hour, files_processed, 4, total_count,
        )
