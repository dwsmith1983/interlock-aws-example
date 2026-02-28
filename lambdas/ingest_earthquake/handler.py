"""Ingest USGS Earthquake data into bronze S3 + write hour-completion MARKERs.

Triggered every 20 minutes by EventBridge. Fetches all earthquakes from the past 24 hours
(all_day feed), groups by data-timestamp par_day/par_hour, writes JSONL to bronze, and
writes hour-completion MARKERs for past hours (not the current hour, which is still
accumulating data). The completion MARKER triggers the DynamoDB stream → stream-router →
SFN validation pipeline.

On first invocation this naturally backfills all available hours from START_DATE onward.
Subsequent runs add incremental data via dedup.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

import requests
from shared.helpers import (
    check_dedup,
    compute_sha256,
    increment_hour_record_count,
    record_dedup,
    upload_to_s3,
    write_hour_complete_marker,
    write_sensor_data,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# all_day covers past 24 hours — enables backfill of all hours since midnight
USGS_ENDPOINT = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"

BUCKET = os.environ["BUCKET_NAME"]
TABLE = os.environ["TABLE_NAME"]
START_DATE = os.environ.get("START_DATE", "20260225")
SOURCE = "earthquake"


def handler(event, context):
    """Fetch USGS earthquake data and write to bronze S3."""
    now = datetime.now(timezone.utc)
    logger.info("ingest-earthquake invoked at %s", now.isoformat())

    # Parse start date cutoff
    try:
        start_dt = datetime.strptime(START_DATE, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        start_dt = datetime(2026, 2, 25, tzinfo=timezone.utc)

    # Fetch USGS GeoJSON (past 24 hours)
    resp = requests.get(USGS_ENDPOINT, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    if not features:
        logger.info("no earthquake features in response")
        return {"statusCode": 200, "body": "no data", "eventCount": 0}

    # Group features by data-timestamp par_day/par_hour, filtering to >= START_DATE
    partitions = defaultdict(list)
    skipped = 0
    for feature in features:
        props = feature.get("properties", {})
        event_time_ms = props.get("time")
        if not event_time_ms:
            continue
        event_dt = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc)
        if event_dt < start_dt:
            skipped += 1
            continue
        par_day = event_dt.strftime("%Y%m%d")
        par_hour = event_dt.strftime("%H")
        partitions[(par_day, par_hour)].append(feature)

    if skipped:
        logger.info("skipped %d events before START_DATE %s", skipped, START_DATE)

    total_events = 0
    uris = []
    current_hour = now.hour

    for (par_day, par_hour), feats in partitions.items():
        # Flatten features to records
        records = [_flatten_feature(f) for f in feats]

        # Build JSONL content
        lines = [json.dumps(r, separators=(",", ":")) for r in records]
        content = ("\n".join(lines) + "\n").encode("utf-8")

        # Dedup check
        content_hash = compute_sha256(content)
        hour_int = int(par_hour)
        if check_dedup(TABLE, SOURCE, par_day, hour_int, content_hash):
            logger.info("duplicate for %s par_day=%s par_hour=%s", SOURCE, par_day, par_hour)
            continue

        # Write to bronze S3
        ts_suffix = now.strftime("%Y%m%dT%H%M%SZ")
        key = f"bronze/{SOURCE}/par_day={par_day}/par_hour={par_hour}/events_{ts_suffix}.jsonl"
        uri = upload_to_s3(BUCKET, key, content)
        uris.append(uri)
        total_events += len(records)

        # Record dedup
        record_dedup(TABLE, SOURCE, par_day, hour_int, content_hash, uri, len(records))
        logger.info("wrote %d events to %s", len(records), uri)

        # Increment per-hour record count sensor
        increment_hour_record_count(TABLE, f"{SOURCE}-silver", par_day, par_hour, len(records))

    # Write hour-completion markers for past hours that received data.
    # Only hours where int(par_hour) != current_hour are complete — the current hour
    # is still accumulating. Event-time partitioning ensures late-arriving records
    # land in the correct hour; future MERGE upserts handle updates.
    for par_day, par_hour in partitions.keys():
        if int(par_hour) != current_hour:
            write_hour_complete_marker(TABLE, f"{SOURCE}-silver", SOURCE, par_day, par_hour)

    # Write sensor data for builtin evaluators
    if total_events > 0:
        all_records = []
        for feats in partitions.values():
            all_records.extend([_flatten_feature(f) for f in feats])
        write_sensor_data(TABLE, "earthquake-silver", "ingest-freshness", {
            "lastIngestTime": now.isoformat(),
            "recordCount": total_events,
            "partitions": len(partitions),
        })
        quality = _compute_quality_metrics(all_records)
        write_sensor_data(TABLE, "earthquake-silver", "ingest-quality", quality)

    return {
        "statusCode": 200,
        "body": f"ingested {total_events} events across {len(partitions)} partitions",
        "eventCount": total_events,
        "partitions": len(partitions),
        "uris": uris,
    }


def _compute_quality_metrics(records: list) -> dict:
    """Compute null rate over key earthquake fields."""
    key_fields = ["earthquake_id", "magnitude", "place", "event_time", "latitude", "longitude"]
    if not records:
        return {"nullRate": 0.0, "schemaDrift": False, "recordCount": 0}
    total_checks = len(records) * len(key_fields)
    null_count = sum(
        1 for r in records for f in key_fields if r.get(f) is None
    )
    return {
        "nullRate": round(null_count / total_checks, 4) if total_checks else 0.0,
        "schemaDrift": False,
        "recordCount": len(records),
    }


def _flatten_feature(feature: dict) -> dict:
    """Flatten a GeoJSON earthquake feature into a flat record."""
    props = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    coords = geometry.get("coordinates", [None, None, None])

    # Parse event_time from epoch ms
    event_time_ms = props.get("time")
    event_time = None
    if event_time_ms:
        event_time = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc).isoformat()

    updated_ms = props.get("updated")
    updated_time = None
    if updated_ms:
        updated_time = datetime.fromtimestamp(updated_ms / 1000, tz=timezone.utc).isoformat()

    return {
        "earthquake_id": feature.get("id"),
        "magnitude": props.get("mag"),
        "place": props.get("place"),
        "event_time": event_time,
        "updated_time": updated_time,
        "event_type": props.get("type"),
        "review_status": props.get("status"),
        "is_tsunami": bool(props.get("tsunami", 0)),
        "significance": props.get("sig"),
        "network": props.get("net"),
        "num_stations": props.get("nst"),
        "min_distance_deg": props.get("dmin"),
        "rms": props.get("rms"),
        "azimuthal_gap": props.get("gap"),
        "magnitude_type": props.get("magType"),
        "alert_level": props.get("alert"),
        "longitude": coords[0] if len(coords) > 0 else None,
        "latitude": coords[1] if len(coords) > 1 else None,
        "depth_km": coords[2] if len(coords) > 2 else None,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
