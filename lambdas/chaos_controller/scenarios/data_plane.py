"""Category 2: Data Plane Chaos — corrupting S3 data and killing jobs.

Scenarios:
- corrupt-bronze: Overwrite a bronze file with invalid JSON
- empty-bronze: Write a 0-byte file to bronze partition
- glue-kill: Stop a running Glue job mid-execution (partial write)
- partial-ingest: Write a single truncated record (simulates Lambda timeout mid-write)
- schema-drift: Write bronze data with renamed fields (simulates upstream API change)
"""

import json
import logging
import random
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
glue = boto3.client("glue")

SOURCES = ["earthquake", "crypto"]


def corrupt_bronze(ctx):
    """Overwrite a bronze file with invalid JSON."""
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    prefix = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/"
    obj = _pick_random_object(bucket, prefix)
    if not obj:
        return {"skipped": True, "reason": f"no objects at {prefix}"}

    corrupt_content = b'{"corrupt": true, "invalid_json_missing_close_brace'
    s3.put_object(Bucket=bucket, Key=obj, Body=corrupt_content, ContentType="application/json")
    logger.info("corrupted bronze object: s3://%s/%s", bucket, obj)
    return {"action": "corrupted", "key": obj}


def empty_bronze(ctx):
    """Write a 0-byte file to a bronze partition."""
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    key = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/chaos_empty_{now.strftime('%H%M%S')}.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body=b"", ContentType="application/json")
    logger.info("wrote empty bronze file: s3://%s/%s", bucket, key)
    return {"action": "empty_write", "key": key}


def glue_kill(ctx):
    """Stop a running Glue job mid-execution, simulating a partial write.

    Delta Lake's ACID guarantees should handle the uncommitted transaction —
    uncommitted files are ignored on the next read. This tests whether the
    pipeline recovers cleanly on the next scheduled run.
    """
    pipeline_id = ctx["pipeline_id"]
    job_name = _glue_job_for_pipeline(pipeline_id)
    if not job_name:
        return {"skipped": True, "reason": f"no Glue job mapping for {pipeline_id}"}

    try:
        resp = glue.get_job_runs(JobName=job_name, MaxResults=5)
    except Exception:
        logger.exception("failed to list job runs for %s", job_name)
        return {"skipped": True, "reason": f"error listing runs for {job_name}"}

    running = [r for r in resp.get("JobRuns", []) if r["JobRunState"] == "RUNNING"]
    if not running:
        return {"skipped": True, "reason": f"no running jobs for {job_name}"}

    target_run = random.choice(running)
    run_id = target_run["Id"]

    try:
        glue.batch_stop_job_run(JobName=job_name, JobRunIds=[run_id])
    except Exception:
        logger.exception("failed to stop Glue job run %s/%s", job_name, run_id)
        return {"skipped": True, "reason": f"error stopping {job_name}/{run_id}"}

    logger.info("killed Glue job run %s/%s (partial write)", job_name, run_id)
    return {"action": "glue_killed", "jobName": job_name, "runId": run_id}


def partial_ingest(ctx):
    """Write a single truncated record to bronze, simulating ingestion Lambda timeout.

    A normal ingestion writes 10+ records per batch. This writes 1 record with
    a truncated final field, as if the Lambda timed out mid-serialization.
    Tests whether silver/gold Glue jobs handle partial source data gracefully.
    """
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    if source == "earthquake":
        record = {
            "earthquake_id": "chaos-partial-001",
            "magnitude": 3.2,
            "place": "Chaos Test Zone",
            "event_time": now.isoformat(),
            "depth_km": 10.5,
            # Truncated: missing most fields that silver expects
        }
    else:
        record = {
            "coin_id": "chaos-partial",
            "symbol": "CHAOS",
            "price_usd": "999.99",
            # Truncated: missing most fields that silver expects
        }

    # Simulate mid-write truncation: valid JSON line but incomplete record
    content = json.dumps(record).encode()
    key = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/chaos_partial_{now.strftime('%H%M%S')}.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/json")
    logger.info("wrote partial-ingest file: s3://%s/%s", bucket, key)
    return {"action": "partial_ingest", "key": key, "source": source}


def schema_drift(ctx):
    """Write bronze data with renamed fields, simulating upstream API schema change.

    Earthquake silver expects: magnitude, place, event_time, earthquake_id, depth_km
    Drifted version uses:      mag, location, time, id, depth

    Crypto silver expects: coin_id, price_usd, market_cap_usd, symbol
    Drifted version uses:  id, price, marketcap, ticker

    Silver Glue jobs cast typed columns (e.g. magnitude→DoubleType) — missing
    columns produce nulls or failures depending on the job's error handling.
    """
    bucket = ctx["bucket_name"]
    now = ctx["now"]
    source = _source_for_pipeline(ctx["pipeline_id"])
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    if source == "earthquake":
        record = {
            "id": "chaos-drift-001",
            "mag": 4.1,
            "location": "Schema Drift Fault Line",
            "time": now.isoformat(),
            "depth": 15.0,
            "updated_time": now.isoformat(),
            "event_type": "earthquake",
            "review_status": "automatic",
            "is_tsunami": False,
            "significance": 200,
            "network": "chaos",
            "num_stations": 5,
            "min_distance_deg": 0.5,
            "rms": 0.1,
            "azimuthal_gap": 90.0,
            "magnitude_type": "ml",
            "alert_level": "",
            "longitude": -122.0,
            "latitude": 37.0,
            "ingested_at": now.isoformat(),
        }
    else:
        record = {
            "id": "chaos-drift",
            "ticker": "CHAOS",
            "name": "ChaosCoin",
            "name_slug": "chaoscoin",
            "market_rank": 999,
            "price": "42.00",
            "pct_change_1h": "0.5",
            "pct_change_24h": "-1.2",
            "pct_change_7d": "3.0",
            "price_btc": "0.0005",
            "marketcap": "1000000",
            "volume_24h_usd": "50000",
            "circulating_supply": "100000",
            "total_supply": "200000",
            "max_supply": "500000",
            "snapshot_time": now.isoformat(),
            "ingested_at": now.isoformat(),
        }

    content = json.dumps(record).encode()
    key = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/chaos_drift_{now.strftime('%H%M%S')}.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/json")
    logger.info("wrote schema-drift file: s3://%s/%s", bucket, key)
    return {"action": "schema_drift", "key": key, "source": source}


# Glue job name mapping: pipeline ID → Glue job name
_GLUE_JOB_MAP = {
    "earthquake-silver": "medallion-silver-earthquake",
    "earthquake-gold": "medallion-gold-earthquake",
    "crypto-silver": "medallion-silver-crypto",
    "crypto-gold": "medallion-gold-crypto",
}


def _glue_job_for_pipeline(pipeline_id):
    """Resolve Glue job name from pipeline ID."""
    return _GLUE_JOB_MAP.get(pipeline_id)


def _source_for_pipeline(pipeline_id):
    """Extract source name from pipeline ID."""
    if "earthquake" in pipeline_id:
        return "earthquake"
    return "crypto"


def _pick_random_object(bucket, prefix):
    """Pick a random object from the given S3 prefix."""
    try:
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=20)
        contents = resp.get("Contents", [])
        if not contents:
            return None
        return random.choice(contents)["Key"]
    except Exception:
        logger.exception("error listing objects at %s", prefix)
        return None
