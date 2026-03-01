import gzip
import json

import boto3

_s3 = boto3.client("s3")


def read_jsonl_gz(bucket: str, key: str) -> list[dict]:
    """Download and decompress a JSONL.gz file from S3, returning parsed records."""
    resp = _s3.get_object(Bucket=bucket, Key=key)
    compressed = resp["Body"].read()
    raw = gzip.decompress(compressed)
    return [json.loads(line) for line in raw.decode().splitlines() if line]
