"""IoT factory sensor consumer Lambda.

Reads machine sensor readings from S3 (triggered via S3 notification),
computes per-machine health status, and writes two types of sensors to the
Interlock control table:

  machine_{id}_status  -- per-machine health and latest values
  factory_health       -- aggregate factory status (derived by querying
                          ALL 10 machine sensors from DynamoDB, not just
                          the machine processed in this invocation)

Each S3 notification triggers this Lambda for a single machine file. To
compute accurate factory-wide health, the handler queries the persisted
status of every machine sensor after writing the current machine's status.
"""

import json
import logging
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3
import botocore.exceptions

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_dynamodb = boto3.client("dynamodb")
_s3 = boto3.client("s3")

_CONTROL_TABLE = os.environ["INTERLOCK_CONTROL_TABLE"]
_S3_BUCKET = os.environ["S3_BUCKET"]
_PIPELINE_ID = os.environ.get("PIPELINE_ID", "iot-factory")
_MACHINE_COUNT = 10

# Thresholds for health classification.
_TEMP_CRITICAL = 75.0
_TEMP_DEGRADED = 60.0
_VIBRATION_CRITICAL = 80.0
_VIBRATION_DEGRADED = 50.0
_PRESSURE_LOW_CRITICAL = 2.0
_PRESSURE_LOW_DEGRADED = 3.0


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
    the banking consumer sensor writing pattern.
    """
    sensor_suffix = f"#{par_day}"
    key = {
        "PK": {"S": f"PIPELINE#{_PIPELINE_ID}"},
        "SK": {"S": f"SENSOR#{sensor_key}{sensor_suffix}"},
    }

    _ensure_data_map(key)

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

    logger.info("iot-consumer: updated sensor %s%s", sensor_key, sensor_suffix)


def _classify_health(
    temperature: float,
    vibration: float,
    pressure: float,
) -> str:
    """Classify machine health as healthy, degraded, or critical."""
    if (
        temperature >= _TEMP_CRITICAL
        or vibration >= _VIBRATION_CRITICAL
        or pressure <= _PRESSURE_LOW_CRITICAL
    ):
        return "critical"
    if (
        temperature >= _TEMP_DEGRADED
        or vibration >= _VIBRATION_DEGRADED
        or pressure <= _PRESSURE_LOW_DEGRADED
    ):
        return "degraded"
    return "healthy"


def _read_readings_from_s3(bucket: str, key: str) -> list[dict]:
    """Read JSONL readings from an S3 object."""
    response = _s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    return [json.loads(line) for line in body.strip().split("\n") if line.strip()]


def _compute_factory_health(
    table_name: str,
    pipeline_id: str,
    par_day: str,
    num_machines: int = 10,
) -> dict:
    """Query all machine sensors from DynamoDB and compute aggregate health.

    Each consumer invocation processes only one S3 file (one machine), so we
    cannot derive factory-wide health from the current invocation alone.
    Instead, we read the latest persisted status for every machine sensor
    and compute the aggregate from that.
    """
    sensor_suffix = f"#{par_day}"
    keys = [
        {
            "PK": {"S": f"PIPELINE#{pipeline_id}"},
            "SK": {"S": f"SENSOR#machine_{i:02d}_status{sensor_suffix}"},
        }
        for i in range(1, num_machines + 1)
    ]

    try:
        resp = _dynamodb.batch_get_item(
            RequestItems={
                table_name: {"Keys": keys, "ConsistentRead": True},
            },
        )
    except botocore.exceptions.ClientError:
        logger.exception("iot-consumer: batch_get_item failed for factory health")
        return {
            "healthy_count": 0,
            "total": num_machines,
            "all_healthy": False,
        }

    items = resp.get("Responses", {}).get(table_name, [])

    # Retry unprocessed keys (DynamoDB throttling)
    unprocessed = resp.get("UnprocessedKeys", {})
    retries = 0
    while unprocessed and retries < 3:
        retries += 1
        resp = _dynamodb.batch_get_item(RequestItems=unprocessed)
        items.extend(resp.get("Responses", {}).get(table_name, []))
        unprocessed = resp.get("UnprocessedKeys", {})

    healthy = sum(
        1
        for item in items
        if item.get("data", {}).get("M", {}).get("status", {}).get("S") == "healthy"
    )
    return {
        "healthy_count": healthy,
        "total": num_machines,
        "all_healthy": healthy == num_machines,
    }


def _compute_machine_status(readings: list[dict]) -> dict:
    """Compute aggregate status for a single machine from its readings."""
    if not readings:
        return {"status": "unknown", "readings_count": 0}

    temps = [r["temperature"] for r in readings]
    vibs = [r["vibration"] for r in readings]
    pressures = [r["pressure"] for r in readings]

    avg_temp = sum(temps) / len(temps)
    avg_vib = sum(vibs) / len(vibs)
    avg_pressure = sum(pressures) / len(pressures)

    status = _classify_health(avg_temp, avg_vib, avg_pressure)

    return {
        "status": status,
        "temperature": round(avg_temp, 2),
        "vibration": round(avg_vib, 2),
        "pressure": round(avg_pressure, 2),
        "readings_count": len(readings),
    }


def lambda_handler(event: dict, context: object) -> dict:
    """Process S3 notification events for IoT sensor readings."""
    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "no records"}

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    par_day = now.strftime("%Y%m%d")

    machines_processed: dict[str, dict] = {}

    for record in records:
        try:
            s3_info = record.get("s3", {})
            bucket = s3_info.get("bucket", {}).get("name", _S3_BUCKET)
            obj_key = unquote_plus(s3_info.get("object", {}).get("key", ""))

            if not obj_key or not obj_key.endswith(".jsonl"):
                continue

            readings = _read_readings_from_s3(bucket, obj_key)
            if not readings:
                continue

            machine_id = readings[0].get("machine_id", "unknown")
            status = _compute_machine_status(readings)
            machines_processed[machine_id] = status

            # Write per-machine sensor.
            try:
                _write_sensor(
                    sensor_key=f"{machine_id}_status",
                    par_day=par_day,
                    metadata={
                        "status": {"S": status["status"]},
                        "temperature": {"N": str(status["temperature"])},
                        "vibration": {"N": str(status["vibration"])},
                        "pressure": {"N": str(status["pressure"])},
                        "readings_count": {"N": str(status["readings_count"])},
                    },
                    now_iso=now_iso,
                )
            except botocore.exceptions.ClientError:
                logger.exception(
                    "iot-consumer: failed to write sensor for %s", machine_id,
                )
        except (botocore.exceptions.ClientError, KeyError, json.JSONDecodeError):
            logger.exception(
                "iot-consumer: failed to process record %s",
                record.get("s3", {}).get("object", {}).get("key", "unknown"),
            )
            continue

    # Compute factory_health by querying ALL machine sensors from DynamoDB.
    # Each invocation only processes one S3 file (one machine), so we
    # cannot derive factory-wide health from machines_processed alone.
    factory = _compute_factory_health(
        _CONTROL_TABLE, _PIPELINE_ID, par_day, _MACHINE_COUNT,
    )

    try:
        _write_sensor(
            sensor_key="factory_health",
            par_day=par_day,
            metadata={
                "healthy_count": {"N": str(factory["healthy_count"])},
                "total": {"N": str(factory["total"])},
                "all_healthy": {"BOOL": factory["all_healthy"]},
            },
            now_iso=now_iso,
        )
    except botocore.exceptions.ClientError:
        logger.exception("iot-consumer: failed to write factory_health sensor")

    logger.info(
        "iot-consumer: processed %d machines this invocation, "
        "factory health: healthy=%d/%d",
        len(machines_processed),
        factory["healthy_count"],
        factory["total"],
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "machines_processed": len(machines_processed),
            "healthy_count": factory["healthy_count"],
            "all_healthy": factory["all_healthy"],
        }),
    }
