"""Ingest CoinLore top-100 cryptocurrency tickers into bronze S3 + write hour-completion MARKER.

Triggered every 20 minutes by EventBridge. Fetches top 100 cryptocurrencies by market cap,
adds snapshot_time, writes JSONL to bronze partitioned by ingestion time. On the last
scheduled run of the hour (minute >= 40), writes an hour-completion MARKER for the current
hour. The completion MARKER triggers the DynamoDB stream → stream-router → SFN pipeline.
"""

import json
import logging
import os
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

COINLORE_ENDPOINT = "https://api.coinlore.net/api/tickers/?start=0&limit=100"

BUCKET = os.environ["BUCKET_NAME"]
TABLE = os.environ["TABLE_NAME"]
START_DATE = os.environ.get("START_DATE", "20260225")
SOURCE = "crypto"


def handler(event, context):
    """Fetch CoinLore ticker data and write to bronze S3."""
    now = datetime.now(timezone.utc)
    snapshot_time = now.isoformat()
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")
    hour_int = int(par_hour)
    logger.info("ingest-crypto invoked at %s", snapshot_time)

    # Check if we're past START_DATE
    try:
        start_dt = datetime.strptime(START_DATE, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        start_dt = datetime(2026, 2, 25, tzinfo=timezone.utc)
    if now < start_dt:
        logger.info("before START_DATE %s, skipping", START_DATE)
        return {"statusCode": 200, "body": "before start date", "tickerCount": 0}

    # Fetch CoinLore tickers
    resp = requests.get(COINLORE_ENDPOINT, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    tickers = data.get("data", [])
    if not tickers:
        logger.info("no ticker data in response")
        return {"statusCode": 200, "body": "no data", "tickerCount": 0}

    # Build records with snapshot_time
    records = []
    for ticker in tickers:
        record = {
            "coin_id": ticker.get("id"),
            "symbol": ticker.get("symbol"),
            "name": ticker.get("name"),
            "name_slug": ticker.get("nameid"),
            "market_rank": ticker.get("rank"),
            "price_usd": ticker.get("price_usd"),
            "pct_change_1h": ticker.get("percent_change_1h"),
            "pct_change_24h": ticker.get("percent_change_24h"),
            "pct_change_7d": ticker.get("percent_change_7d"),
            "price_btc": ticker.get("price_btc"),
            "market_cap_usd": ticker.get("market_cap_usd"),
            "volume_24h_usd": ticker.get("volume24"),
            "circulating_supply": ticker.get("csupply"),
            "total_supply": ticker.get("tsupply"),
            "max_supply": ticker.get("msupply"),
            "snapshot_time": snapshot_time,
            "ingested_at": snapshot_time,
        }
        records.append(record)

    # Build JSONL content
    lines = [json.dumps(r, separators=(",", ":")) for r in records]
    content = ("\n".join(lines) + "\n").encode("utf-8")

    # Dedup check
    content_hash = compute_sha256(content)
    if check_dedup(TABLE, SOURCE, par_day, hour_int, content_hash):
        logger.info("duplicate for %s par_day=%s par_hour=%s", SOURCE, par_day, par_hour)
        return {"statusCode": 200, "body": "duplicate", "tickerCount": 0}

    # Write to bronze S3
    ts_suffix = now.strftime("%Y%m%dT%H%M%SZ")
    key = f"bronze/{SOURCE}/par_day={par_day}/par_hour={par_hour}/tickers_{ts_suffix}.jsonl"
    uri = upload_to_s3(BUCKET, key, content)

    # Record dedup
    record_dedup(TABLE, SOURCE, par_day, hour_int, content_hash, uri, len(records))
    logger.info("wrote %d tickers to %s", len(records), uri)

    # Increment per-hour record count sensor
    increment_hour_record_count(TABLE, f"{SOURCE}-silver", par_day, par_hour, len(records))

    # Write hour-completion marker on the last scheduled run of the hour.
    # With 20-min cadence (:00, :20, :40), the :40 run is the final ingestion for this hour.
    if now.minute >= 40:
        write_hour_complete_marker(TABLE, f"{SOURCE}-silver", SOURCE, par_day, par_hour)

    # Write sensor data for builtin evaluators
    quality = _compute_quality_metrics(records)
    write_sensor_data(TABLE, "crypto-silver", "ingest-freshness", {
        "lastIngestTime": snapshot_time,
        "recordCount": len(records),
    })
    write_sensor_data(TABLE, "crypto-silver", "ingest-quality", quality)

    return {
        "statusCode": 200,
        "body": f"ingested {len(records)} tickers",
        "tickerCount": len(records),
        "uri": uri,
    }


def _compute_quality_metrics(records: list) -> dict:
    """Compute null rate over key crypto fields."""
    key_fields = ["coin_id", "symbol", "name", "price_usd", "market_cap_usd", "volume_24h_usd"]
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
