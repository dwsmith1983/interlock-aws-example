import gzip
import json
from datetime import datetime

import boto3

from generator.sessions import generate_window

CHUNK_SIZE = 100_000


def gzip_jsonl(records: list[dict]) -> bytes:
    payload = "\n".join(json.dumps(r) for r in records).encode()
    return gzip.compress(payload)


def upload_to_s3(bucket: str, key: str, data: bytes) -> None:
    client = boto3.client("s3")
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/gzip")


def generate_and_upload(
    stream: str, window_start: datetime, daily_target: int, bucket: str
) -> dict:
    records = generate_window(stream, window_start, daily_target)

    # Group records by actual timestamp hour for correct partitioning.
    # With expanded spillover, records may span adjacent hours.
    by_partition: dict[tuple[str, str], list[dict]] = {}
    for rec in records:
        t = rec["time"]  # "YYYY-MM-DDTHH:MM:SSZ"
        rec_date = t[:4] + t[5:7] + t[8:10]  # YYYYMMDD
        rec_hour = t[11:13]                    # HH
        by_partition.setdefault((rec_date, rec_hour), []).append(rec)

    time_str = window_start.strftime("%H%M")
    files_uploaded = 0
    total_records = len(records)

    for (date_str, hour_str), hour_records in sorted(by_partition.items()):
        for i in range(0, max(1, len(hour_records)), CHUNK_SIZE):
            chunk = hour_records[i : i + CHUNK_SIZE]
            if not chunk:
                break
            part = (i // CHUNK_SIZE) + 1
            key = (
                f"{stream}/par_day={date_str}/par_hour={hour_str}/"
                f"{stream}_{date_str}_{time_str}_{part:04d}.jsonl.gz"
            )
            upload_to_s3(bucket, key, gzip_jsonl(chunk))
            files_uploaded += 1

    return {
        "stream": stream,
        "window": window_start.isoformat(),
        "total_records": total_records,
        "files": files_uploaded,
        "bucket": bucket,
    }
