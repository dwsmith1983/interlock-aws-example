"""Category 4: Trigger & Cascade Chaos — ordering/timing.

Scenarios:
- dup-marker: Write identical MARKER twice
- burst-markers: Write 5 MARKERs for same pipeline/schedule rapidly
- late-data: Write bronze data with par_hour from 2-3 hours ago + MARKER
- orphan-marker: Write MARKER for nonexistent pipeline
"""

import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger(__name__)

ddb = boto3.client("dynamodb")
s3 = boto3.client("s3")


def dup_marker(ctx):
    """Write identical MARKER twice within 1 second."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    for i in range(2):
        _write_marker(table, pipeline_id, schedule_id, now)
        if i == 0:
            time.sleep(0.5)

    logger.info("wrote duplicate MARKERs for %s/%s", pipeline_id, schedule_id)
    return {"action": "dup_marker", "pipeline": pipeline_id, "schedule": schedule_id, "count": 2}


def burst_markers(ctx):
    """Write 5 MARKERs for same pipeline/schedule rapidly."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    date = now.strftime("%Y%m%d")
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    # Only inject if there's an active run for this schedule
    if not _has_active_run(table, pipeline_id, date, schedule_id):
        logger.info("no active run for %s/%s, skipping burst-markers", pipeline_id, schedule_id)
        return {"skipped": True, "reason": "no active data"}

    for i in range(5):
        _write_marker(table, pipeline_id, schedule_id, now, suffix=f"burst{i}")

    logger.info("wrote 5 burst MARKERs for %s/%s", pipeline_id, schedule_id)
    return {"action": "burst_markers", "pipeline": pipeline_id, "schedule": schedule_id, "count": 5}


def late_data(ctx):
    """Write bronze data with par_hour from 2-3 hours ago + corresponding MARKER."""
    table = ctx["table_name"]
    bucket = ctx["bucket_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]

    hours_ago = random.choice([2, 3])
    past_time = now - timedelta(hours=hours_ago)
    par_day = past_time.strftime("%Y%m%d")
    par_hour = past_time.strftime("%H")

    source = "earthquake" if "earthquake" in pipeline_id else "crypto"

    # Write late bronze data
    content = json.dumps({
        "chaos": True,
        "scenario": "late-data",
        "hoursLate": hours_ago,
        "timestamp": now.isoformat(),
    }).encode()
    key = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/chaos_late_{now.strftime('%H%M%S')}.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/json")

    # Write MARKER for the late schedule
    silver_pipeline = f"{source}-silver"
    schedule_id = f"h{par_hour}"
    _write_marker(table, silver_pipeline, schedule_id, now)

    logger.info("wrote late data (%dh ago) for %s/%s", hours_ago, silver_pipeline, schedule_id)
    return {
        "action": "late_data",
        "key": key,
        "pipeline": silver_pipeline,
        "schedule": schedule_id,
        "hoursLate": hours_ago,
    }


def orphan_marker(ctx):
    """Write MARKER for a nonexistent pipeline."""
    table = ctx["table_name"]
    now = ctx["now"]
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    fake_pipeline = "nonexistent-chaos-pipeline"
    _write_marker(table, fake_pipeline, schedule_id, now)
    logger.info("wrote orphan MARKER for %s/%s", fake_pipeline, schedule_id)
    return {"action": "orphan_marker", "pipeline": fake_pipeline, "schedule": schedule_id}


def _has_active_run(table, pipeline_id, date, schedule_id):
    """Check if there's a RUNLOG entry for this pipeline/schedule today."""
    pk = f"PIPELINE#{pipeline_id}"
    sk = f"RUNLOG#{date}#{schedule_id}"
    try:
        resp = ddb.get_item(
            TableName=table,
            Key={"PK": {"S": pk}, "SK": {"S": sk}},
            ProjectionExpression="PK",
        )
        return "Item" in resp
    except Exception:
        logger.exception("error checking active run for %s/%s", pipeline_id, schedule_id)
        return False


def _write_marker(table, pipeline_id, schedule_id, now, suffix=""):
    """Write a MARKER record to DynamoDB."""
    ts = now.isoformat()
    ttl = int(now.timestamp()) + 86400
    sk_ts = f"{ts}_{suffix}" if suffix else ts

    ddb.put_item(
        TableName=table,
        Item={
            "PK": {"S": f"PIPELINE#{pipeline_id}"},
            "SK": {"S": f"MARKER#chaos#{sk_ts}"},
            "scheduleID": {"S": schedule_id},
            "timestamp": {"S": ts},
            "ttl": {"N": str(ttl)},
        },
    )
