"""IoT factory sensor generator Lambda.

Simulates 10 factory machines with temperature, vibration, and pressure
sensors.  Generates one minute of readings per invocation (or 5 minutes
when triggered by EventBridge on a 5-minute schedule).

Uses a seeded PRNG for reproducibility when RANDOM_SEED is set.
"""

import json
import logging
import os
import random
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")

_S3_BUCKET = os.environ["S3_BUCKET"]
_ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
_RANDOM_SEED = os.environ.get("RANDOM_SEED")
_MACHINE_COUNT = 10
_MINUTES_PER_INVOCATION = 5


def _generate_reading(
    rng: random.Random,
    machine_id: int,
    timestamp_iso: str,
) -> dict:
    """Generate a single sensor reading for one machine."""
    return {
        "machine_id": f"machine_{machine_id:02d}",
        "timestamp": timestamp_iso,
        "temperature": round(rng.uniform(20.0, 80.0), 2),
        "vibration": round(rng.uniform(0.0, 100.0), 2),
        "pressure": round(rng.uniform(1.0, 10.0), 2),
        "environment": _ENVIRONMENT,
    }


def _generate_readings_for_window(
    rng: random.Random,
    base_time: datetime,
    minutes: int,
) -> dict[str, list[dict]]:
    """Generate readings for all machines over a time window.

    Returns a dict keyed by machine_id with lists of readings.
    """
    readings_by_machine: dict[str, list[dict]] = {}

    for minute_offset in range(minutes):
        ts = base_time + timedelta(minutes=minute_offset)
        ts_iso = ts.isoformat()

        for machine_id in range(1, _MACHINE_COUNT + 1):
            machine_key = f"machine_{machine_id:02d}"
            reading = _generate_reading(rng, machine_id, ts_iso)

            if machine_key not in readings_by_machine:
                readings_by_machine[machine_key] = []
            readings_by_machine[machine_key].append(reading)

    return readings_by_machine


def _write_readings_to_s3(
    readings_by_machine: dict[str, list[dict]],
    base_time: datetime,
) -> int:
    """Write JSONL files to S3, one per machine.

    S3 path: iot/readings/par_day=YYYYMMDD/par_hour=HH/machine_{id}.jsonl

    Returns total readings written.
    """
    par_day = base_time.strftime("%Y%m%d")
    par_hour = base_time.strftime("%H")
    total = 0

    for machine_key, readings in readings_by_machine.items():
        jsonl = "\n".join(json.dumps(r) for r in readings)
        s3_key = (
            f"iot/readings/par_day={par_day}/par_hour={par_hour}"
            f"/{machine_key}.jsonl"
        )
        _s3.put_object(
            Bucket=_S3_BUCKET,
            Key=s3_key,
            Body=jsonl.encode("utf-8"),
            ContentType="application/x-ndjson",
        )
        total += len(readings)

    return total


def lambda_handler(event: dict, context: object) -> dict:
    """Generate factory sensor readings and write to S3."""
    rng = random.Random(_RANDOM_SEED) if _RANDOM_SEED else random.Random()

    now = datetime.now(timezone.utc)
    base_time = now - timedelta(minutes=_MINUTES_PER_INVOCATION)

    readings_by_machine = _generate_readings_for_window(
        rng, base_time, _MINUTES_PER_INVOCATION,
    )
    total = _write_readings_to_s3(readings_by_machine, base_time)

    logger.info(
        "iot-generator: wrote %d readings for %d machines",
        total,
        _MACHINE_COUNT,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "readings_written": total,
            "machine_count": _MACHINE_COUNT,
            "timestamp": now.isoformat(),
        }),
    }
