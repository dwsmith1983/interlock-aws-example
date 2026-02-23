"""Shared helpers for ingestion Lambdas: dedup, MARKER writing, S3 upload."""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
ddb = boto3.client("dynamodb")


def compute_sha256(content: bytes) -> str:
    """Return hex SHA-256 digest of content."""
    return hashlib.sha256(content).hexdigest()


def check_dedup(table_name: str, source: str, date: str, hour: int, content_hash: str) -> bool:
    """Check if this content has already been ingested.

    Returns True if duplicate (already exists), False if new.
    """
    pk = f"DEDUP#{source}"
    sk = f"{date}#{hour:02d}#{content_hash}"

    resp = ddb.get_item(
        TableName=table_name,
        Key={
            "PK": {"S": pk},
            "SK": {"S": sk},
        },
    )
    return "Item" in resp


def record_dedup(
    table_name: str,
    source: str,
    date: str,
    hour: int,
    content_hash: str,
    s3_uri: str,
    record_count: int,
    ttl_days: int = 7,
) -> bool:
    """Write a dedup record with conditional put. Returns True if written, False if race lost."""
    pk = f"DEDUP#{source}"
    sk = f"{date}#{hour:02d}#{content_hash}"
    now = datetime.now(timezone.utc)
    ttl = int(now.timestamp()) + (ttl_days * 86400)

    try:
        ddb.put_item(
            TableName=table_name,
            Item={
                "PK": {"S": pk},
                "SK": {"S": sk},
                "uri": {"S": s3_uri},
                "recordCount": {"N": str(record_count)},
                "ingestedAt": {"S": now.isoformat()},
                "ttl": {"N": str(ttl)},
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info("dedup race: record already exists for %s/%s", source, sk)
            return False
        raise


def upload_to_s3(bucket: str, key: str, body: bytes, content_type: str = "application/json") -> str:
    """Upload content to S3 and return the S3 URI."""
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    return f"s3://{bucket}/{key}"


def write_marker(
    table_name: str,
    pipeline_id: str,
    source_name: str,
    schedule_id: str,
):
    """Write a MARKER record to DynamoDB to trigger the interlock Step Function.

    The stream-router reads scheduleID from NewImage to build per-hour dedup keys.
    """
    now = datetime.now(timezone.utc)
    ts = now.isoformat()
    ttl = int(now.timestamp()) + 86400  # 24h TTL

    pk = f"PIPELINE#{pipeline_id}"
    sk = f"MARKER#{source_name}#{ts}"

    ddb.put_item(
        TableName=table_name,
        Item={
            "PK": {"S": pk},
            "SK": {"S": sk},
            "scheduleID": {"S": schedule_id},
            "timestamp": {"S": ts},
            "ttl": {"N": str(ttl)},
        },
    )
    logger.info("wrote MARKER for %s schedule=%s", pipeline_id, schedule_id)


class HourTracker:
    """Tracks which hour we last wrote a MARKER for, to write at most once per hour turn."""

    def __init__(self):
        self._last_marker_hour = None

    def should_write_marker(self, current_hour: int) -> bool:
        """Returns True if this is a new hour we haven't written a MARKER for."""
        if self._last_marker_hour != current_hour:
            self._last_marker_hour = current_hour
            return True
        return False
