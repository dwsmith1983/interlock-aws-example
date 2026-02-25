"""Category 4: Trigger & Cascade Chaos — ordering/timing.

Scenarios:
- dup-marker: Write identical MARKER twice
- burst-markers: Write 5 MARKERs for same pipeline/schedule rapidly
- future-marker: Write MARKER with scheduleID for next hour
- late-data: Write bronze data with par_hour from 2-3 hours ago + MARKER
- delete-upstream-runlog: Delete upstream silver RUNLOG before gold evaluates
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
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    for i in range(5):
        _write_marker(table, pipeline_id, schedule_id, now, suffix=f"burst{i}")

    logger.info("wrote 5 burst MARKERs for %s/%s", pipeline_id, schedule_id)
    return {"action": "burst_markers", "pipeline": pipeline_id, "schedule": schedule_id, "count": 5}


def future_marker(ctx):
    """Write MARKER with scheduleID for next hour."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    next_hour = (now + timedelta(hours=1)).strftime("%H")
    schedule_id = f"h{next_hour}"

    _write_marker(table, pipeline_id, schedule_id, now)
    logger.info("wrote future MARKER for %s/%s", pipeline_id, schedule_id)
    return {"action": "future_marker", "pipeline": pipeline_id, "schedule": schedule_id}


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


def delete_upstream_runlog(ctx):
    """Delete upstream silver RUNLOG after silver completes, before gold evaluates."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    date = now.strftime("%Y%m%d")
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    # Determine upstream silver pipeline
    if "gold" not in pipeline_id:
        return {"skipped": True, "reason": f"{pipeline_id} is not a gold pipeline"}

    upstream = pipeline_id.replace("-gold", "-silver")
    pk = f"PIPELINE#{upstream}"
    sk = f"RUNLOG#{date}#{schedule_id}"

    try:
        resp = ddb.get_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        if "Item" not in resp:
            return {"skipped": True, "reason": f"no RUNLOG for {upstream}/{schedule_id}"}

        ddb.delete_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        logger.info("deleted upstream RUNLOG for %s/%s", upstream, schedule_id)
        return {"action": "deleted_upstream_runlog", "upstream": upstream, "schedule": schedule_id}
    except Exception:
        logger.exception("error deleting upstream RUNLOG")
        return {"skipped": True, "reason": "error"}


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
