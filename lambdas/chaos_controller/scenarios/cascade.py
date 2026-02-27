"""Category 4: Trigger & Cascade Chaos — ordering/timing.

Scenarios:
- dup-marker: Write identical MARKER twice (at-least-once delivery replay)
- late-data: Write bronze data for H-1 (previous completed hour) + MARKER
- stale-reprocess: Write MARKER for a pipeline+schedule that already completed
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

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


def late_data(ctx):
    """Write bronze data for the previous completed hour (H-1) + MARKER.

    This is the exact real-world scenario: data for an hour block arriving
    after that hour was already processed by the silver pipeline.
    """
    table = ctx["table_name"]
    bucket = ctx["bucket_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]

    # H-1: the previous hour that should already be processed
    past_time = now - timedelta(hours=1)
    par_day = past_time.strftime("%Y%m%d")
    par_hour = past_time.strftime("%H")

    source = "earthquake" if "earthquake" in pipeline_id else "crypto"

    # Write late bronze data
    content = json.dumps({
        "chaos": True,
        "scenario": "late-data",
        "hoursLate": 1,
        "timestamp": now.isoformat(),
    }).encode()
    key = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/chaos_late_{now.strftime('%H%M%S')}.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/json")

    # Write MARKER for the late schedule targeting the silver pipeline
    silver_pipeline = f"{source}-silver"
    schedule_id = f"h{par_hour}"
    _write_marker(table, silver_pipeline, schedule_id, now)

    logger.info("wrote late data (H-1) for %s/%s", silver_pipeline, schedule_id)
    return {
        "action": "late_data",
        "key": key,
        "pipeline": silver_pipeline,
        "schedule": schedule_id,
        "hoursLate": 1,
    }


def stale_reprocess(ctx):
    """Write MARKER for a pipeline+schedule that already has a COMPLETED RUNLOG.

    Simulates a delayed EventBridge trigger or DynamoDB Streams replay after
    the pipeline already finished. Tests that checkRunLog correctly handles
    re-triggers of completed work.
    """
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    date = now.strftime("%Y%m%d")
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    pk = f"PIPELINE#{pipeline_id}"
    sk = f"RUNLOG#{date}#{schedule_id}"

    # Only inject if there's a COMPLETED RUNLOG for this schedule
    try:
        resp = ddb.get_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        item = resp.get("Item")
        if not item:
            return {"skipped": True, "reason": f"no RUNLOG for {pipeline_id}/{schedule_id}"}

        data = json.loads(item.get("data", {}).get("S", "{}"))
        if data.get("status") != "COMPLETED":
            return {"skipped": True, "reason": f"RUNLOG status is {data.get('status')}, not COMPLETED"}
    except ClientError:
        logger.exception("error checking RUNLOG for %s/%s", pipeline_id, schedule_id)
        return {"skipped": True, "reason": "error"}

    # Write MARKER for the already-completed schedule
    _write_marker(table, pipeline_id, schedule_id, now, suffix="stale")
    logger.info("wrote stale-reprocess MARKER for %s/%s (already COMPLETED)", pipeline_id, schedule_id)
    return {"action": "stale_reprocess", "pipeline": pipeline_id, "schedule": schedule_id}


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
