"""GH Archive ingestion Lambda.

Triggered hourly by EventBridge. Downloads the previous hour's archive file
from data.gharchive.org, writes to S3 bronze, and writes a MARKER.
"""

import gzip
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO

import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

import sys
sys.path.insert(0, "/opt/python")
from shared.helpers import (
    check_dedup,
    compute_sha256,
    record_dedup,
    upload_to_s3,
    write_marker,
)

BUCKET = os.environ["BUCKET_NAME"]
TABLE = os.environ["TABLE_NAME"]
PIPELINE_ID = "gharchive-silver"
BASE_URL = "https://data.gharchive.org"


def handler(event, context):
    """Download previous hour's GH Archive and write to bronze."""
    now = datetime.now(timezone.utc)
    # Download the previous hour's archive (published with ~5 min delay)
    target = now - timedelta(hours=1)
    date = target.strftime("%Y-%m-%d")
    hour = target.hour

    archive_url = f"{BASE_URL}/{date}-{hour}.json.gz"
    url_hash = compute_sha256(archive_url.encode())

    # Check dedup by URL hash first (fast path)
    if check_dedup(TABLE, "gharchive", date, hour, url_hash):
        logger.info("already ingested %s", archive_url)
        return {"statusCode": 200, "body": "duplicate"}

    # Download the archive
    logger.info("downloading %s", archive_url)
    try:
        resp = requests.get(archive_url, timeout=120)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error("failed to download %s: %s", archive_url, e)
        return {"statusCode": 500, "body": f"download failed: {e}"}

    raw_data = resp.content
    content_hash = compute_sha256(raw_data)

    # Combine URL hash + content hash for definitive dedup
    combined_hash = compute_sha256(f"{url_hash}:{content_hash}".encode())
    if check_dedup(TABLE, "gharchive", date, hour, combined_hash):
        logger.info("content already ingested for %s", archive_url)
        return {"statusCode": 200, "body": "duplicate"}

    # Count records (for metadata)
    record_count = 0
    try:
        with gzip.open(BytesIO(raw_data)) as f:
            for _ in f:
                record_count += 1
    except Exception as e:
        logger.warning("failed to count records: %s", e)

    # Write compressed archive directly to S3
    key = f"bronze/gharchive/dt={date}/hh={hour:02d}/events.jsonl.gz"
    s3_uri = upload_to_s3(BUCKET, key, raw_data, content_type="application/gzip")

    record_dedup(TABLE, "gharchive", date, hour, combined_hash, s3_uri, record_count)
    logger.info("wrote %d events to %s", record_count, s3_uri)

    # Write MARKER for the ingested hour
    schedule_id = f"h{hour:02d}"
    write_marker(TABLE, PIPELINE_ID, "ingest-complete", schedule_id)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "events": record_count,
            "s3_uri": s3_uri,
            "hour": hour,
        }),
    }
