"""Open-Meteo weather data ingestion Lambda.

Triggered hourly by EventBridge. Fetches current weather for 10 cities
from the Open-Meteo API, writes to S3 bronze, and writes a MARKER.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

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
PIPELINE_ID = "openmeteo-silver"

# 10 cities with their coordinates
CITIES = [
    {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    {"name": "London", "lat": 51.5074, "lon": -0.1278},
    {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    {"name": "Sydney", "lat": -33.8688, "lon": 151.2093},
    {"name": "Paris", "lat": 48.8566, "lon": 2.3522},
    {"name": "Berlin", "lat": 52.5200, "lon": 13.4050},
    {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    {"name": "São Paulo", "lat": -23.5505, "lon": -46.6333},
    {"name": "Cairo", "lat": 30.0444, "lon": 31.2357},
    {"name": "Toronto", "lat": 43.6532, "lon": -79.3832},
]

API_BASE = "https://api.open-meteo.com/v1/forecast"


def handler(event, context):
    """Fetch current weather for 10 cities and write to bronze."""
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    hour = now.hour

    # Build dedup key from date + hour + sorted city list
    city_names = sorted(c["name"] for c in CITIES)
    dedup_input = f"{date}#{hour:02d}#{','.join(city_names)}"

    records = []
    for city in CITIES:
        try:
            data = _fetch_weather(city, date)
            data["city"] = city["name"]
            data["fetched_at"] = now.isoformat()
            records.append(data)
        except Exception as e:
            logger.warning("failed to fetch weather for %s: %s", city["name"], e)

    if not records:
        logger.error("no weather data collected")
        return {"statusCode": 500, "body": "no data collected"}

    # Compute content hash
    content = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    content_hash = compute_sha256(content)
    combined_hash = compute_sha256(f"{dedup_input}:{content_hash}".encode())

    if check_dedup(TABLE, "openmeteo", date, hour, combined_hash):
        logger.info("already ingested weather data for %s hour %d", date, hour)
        return {"statusCode": 200, "body": "duplicate"}

    # Write JSONL to S3
    jsonl = "\n".join(json.dumps(r, separators=(",", ":")) for r in records)
    body = jsonl.encode("utf-8")
    key = f"bronze/openmeteo/dt={date}/hh={hour:02d}/forecast.jsonl"
    s3_uri = upload_to_s3(BUCKET, key, body)

    record_dedup(TABLE, "openmeteo", date, hour, combined_hash, s3_uri, len(records))
    logger.info("wrote %d weather records to %s", len(records), s3_uri)

    # Write MARKER
    schedule_id = f"h{hour:02d}"
    write_marker(TABLE, PIPELINE_ID, "ingest-complete", schedule_id)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "records": len(records),
            "s3_uri": s3_uri,
            "hour": hour,
        }),
    }


def _fetch_weather(city, date):
    """Fetch current weather from Open-Meteo API for a single city."""
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code",
        "temperature_unit": "celsius",
        "timezone": "UTC",
    }
    resp = requests.get(API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
