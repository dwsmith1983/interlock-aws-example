"""IoT factory aggregator Lambda.

Triggered by interlock when all machines are healthy and sensors are fresh.
Reads hourly readings from S3, computes factory-wide metrics, and writes
a summary JSON file.
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")

_S3_BUCKET = os.environ["S3_BUCKET"]
_ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


def _list_readings_for_hour(par_day: str, par_hour: str) -> list[str]:
    """List all JSONL reading files for a given hour."""
    prefix = f"iot/readings/par_day={par_day}/par_hour={par_hour}/"
    paginator = _s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=_S3_BUCKET, Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return keys


def _read_jsonl(key: str) -> list[dict]:
    """Read a JSONL file from S3."""
    response = _s3.get_object(Bucket=_S3_BUCKET, Key=key)
    body = response["Body"].read().decode("utf-8")
    return [json.loads(line) for line in body.strip().split("\n") if line.strip()]


def _aggregate_readings(all_readings: list[dict]) -> dict:
    """Compute factory-wide metrics from all readings."""
    if not all_readings:
        return {
            "total_readings": 0,
            "machine_count": 0,
            "avg_temperature": 0.0,
            "avg_vibration": 0.0,
            "avg_pressure": 0.0,
        }

    temps = [r.get("temperature", 0.0) for r in all_readings]
    vibs = [r.get("vibration", 0.0) for r in all_readings]
    pressures = [r.get("pressure", 0.0) for r in all_readings]
    machines = {r["machine_id"] for r in all_readings}

    return {
        "total_readings": len(all_readings),
        "machine_count": len(machines),
        "avg_temperature": round(sum(temps) / len(temps), 2),
        "avg_vibration": round(sum(vibs) / len(vibs), 2),
        "avg_pressure": round(sum(pressures) / len(pressures), 2),
        "max_temperature": round(max(temps), 2),
        "max_vibration": round(max(vibs), 2),
        "min_pressure": round(min(pressures), 2),
    }


def lambda_handler(event: dict, context: object) -> dict:
    """Aggregate hourly readings and write factory summary."""
    now = datetime.now(timezone.utc)
    par_day = event.get("par_day") or now.strftime("%Y%m%d")
    par_hour = event.get("par_hour") or now.strftime("%H")

    # Read all reading files for the current hour.
    reading_keys = _list_readings_for_hour(par_day, par_hour)

    all_readings: list[dict] = []
    for key in reading_keys:
        all_readings.extend(_read_jsonl(key))

    summary = {
        **_aggregate_readings(all_readings),
        "par_day": par_day,
        "par_hour": par_hour,
        "aggregated_at": now.isoformat(),
        "environment": _ENVIRONMENT,
    }

    # Write summary to S3.
    summary_key = (
        f"iot/aggregated/par_day={par_day}/par_hour={par_hour}/summary.json"
    )
    _s3.put_object(
        Bucket=_S3_BUCKET,
        Key=summary_key,
        Body=json.dumps(summary).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        "iot-aggregator: wrote summary for %s/%s (%d readings, %d machines)",
        par_day,
        par_hour,
        summary["total_readings"],
        summary["machine_count"],
    )

    return {
        "statusCode": 200,
        "body": json.dumps(summary),
    }
