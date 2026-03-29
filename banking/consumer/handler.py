"""Banking stream consumer Lambda.

Processes Kinesis records, writes aggregated output to S3, and updates two
Interlock sensors in the control table:

  consumer_lag  -- {lag_seconds: N, updated_at: T}
  cob_status    -- {complete: true/false, updated_at: T}

Lag is the difference between current time and the oldest record timestamp.
COB is considered complete when the current hour exceeds COB_HOUR (16:00 ET
by default, expressed in UTC as 21 or configurable).
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
import botocore.exceptions

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_dynamodb = boto3.client("dynamodb")
_s3 = boto3.client("s3")

_CONTROL_TABLE = os.environ["INTERLOCK_CONTROL_TABLE"]
_OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
_COB_HOUR = int(os.environ.get("COB_HOUR", "17"))
_PIPELINE_ID = "banking-streaming"


def _ensure_data_map(key: dict) -> None:
    """Ensure the nested data map exists on the sensor record."""
    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression="SET #data = if_not_exists(#data, :empty_map)",
        ExpressionAttributeNames={"#data": "data"},
        ExpressionAttributeValues={":empty_map": {"M": {}}},
    )


def _write_sensor(
    sensor_key: str,
    par_day: str,
    metadata: dict[str, dict],
    now_iso: str,
) -> None:
    """Write a sensor record to the Interlock control table.

    Uses the low-level DynamoDB client with atomic updates, consistent with
    the dryrun_demo sensor writing pattern.
    """
    sensor_suffix = f"#{par_day}"
    key = {
        "PK": {"S": f"PIPELINE#{_PIPELINE_ID}"},
        "SK": {"S": f"SENSOR#{sensor_key}{sensor_suffix}"},
    }

    _ensure_data_map(key)

    # Build SET and expression attribute pairs from metadata.
    set_parts = ["#data.updatedAt = :now"]
    attr_names: dict[str, str] = {"#data": "data"}
    attr_values: dict[str, dict] = {":now": {"S": now_iso}}

    for field_name, field_value in metadata.items():
        placeholder = f"#{field_name}"
        value_placeholder = f":{field_name}"
        attr_names[placeholder] = field_name
        attr_values[value_placeholder] = field_value
        set_parts.append(f"#data.{placeholder} = {value_placeholder}")

    update_expr = "SET " + ", ".join(set_parts)

    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression=update_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )

    logger.info(
        "banking-consumer: updated sensor %s%s",
        sensor_key,
        sensor_suffix,
    )


def _write_processed_batch(
    transaction_count: int,
    now: datetime,
) -> None:
    """Write the processed batch summary to S3."""
    date_prefix = now.strftime("%Y-%m-%d")
    hour_prefix = now.strftime("%H")
    key = (
        f"banking/processed/{date_prefix}/{hour_prefix}"
        f"/batch-{int(now.timestamp())}.json"
    )
    _s3.put_object(
        Bucket=_OUTPUT_BUCKET,
        Key=key,
        Body=json.dumps({
            "count": transaction_count,
            "timestamp": now.isoformat(),
        }),
        ContentType="application/json",
    )


def lambda_handler(event: dict, context: object) -> dict:
    """Process Kinesis records and update Interlock sensors."""
    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "no records"}

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    par_day = now.strftime("%Y%m%d")

    # Calculate lag from the oldest record in the batch.
    oldest_timestamp: datetime | None = None
    transaction_count = 0

    for record in records:
        raw_data = record["kinesis"]["data"]
        payload = json.loads(raw_data)
        txn_time = datetime.fromisoformat(payload["timestamp"])
        if oldest_timestamp is None or txn_time < oldest_timestamp:
            oldest_timestamp = txn_time
        transaction_count += 1

    lag_seconds = (
        int((now - oldest_timestamp).total_seconds())
        if oldest_timestamp is not None
        else 0
    )

    # Write processed data to S3.
    _write_processed_batch(transaction_count, now)

    # Update consumer_lag sensor.
    _write_sensor(
        sensor_key="consumer_lag",
        par_day=par_day,
        metadata={
            "lag_seconds": {"N": str(lag_seconds)},
        },
        now_iso=now_iso,
    )

    # Update cob_status sensor.
    # COB is complete once we've passed the COB hour.
    is_cob_complete = now.hour > _COB_HOUR

    cob_metadata: dict[str, dict] = {
        "complete": {"BOOL": is_cob_complete},
    }

    _write_sensor(
        sensor_key="cob_status",
        par_day=par_day,
        metadata=cob_metadata,
        now_iso=now_iso,
    )

    logger.info(
        "banking-consumer: processed %d records, lag=%ds, cob_complete=%s",
        transaction_count,
        lag_seconds,
        is_cob_complete,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "processed": transaction_count,
            "lag_seconds": lag_seconds,
            "cob_complete": is_cob_complete,
        }),
    }
