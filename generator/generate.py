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

    date_str = window_start.strftime("%Y%m%d")
    hour_str = window_start.strftime("%H")
    time_str = window_start.strftime("%H%M")

    files_uploaded = 0
    for i in range(0, max(1, len(records)), CHUNK_SIZE):
        chunk = records[i : i + CHUNK_SIZE]
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
        "total_records": len(records),
        "files": files_uploaded,
        "bucket": bucket,
    }
