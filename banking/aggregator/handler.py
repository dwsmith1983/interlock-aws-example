"""Banking aggregation Lambda.

Simple downstream job triggered by Interlock when cob_status.complete=true
AND consumer_lag.lag_seconds<=300.  Aggregates the day's processed data into
a daily summary.  This Lambda proves the trigger pipeline works end-to-end.
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")

_OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def lambda_handler(event: dict, context: object) -> dict:
    """Aggregate daily banking transactions."""
    now = datetime.now(timezone.utc)
    date_prefix = now.strftime("%Y-%m-%d")

    # List all processed batches for today.
    prefix = f"banking/processed/{date_prefix}/"
    response = _s3.list_objects_v2(Bucket=_OUTPUT_BUCKET, Prefix=prefix)

    batch_count = 0
    total_transactions = 0

    for obj in response.get("Contents", []):
        data = _s3.get_object(Bucket=_OUTPUT_BUCKET, Key=obj["Key"])
        body = json.loads(data["Body"].read())
        total_transactions += body.get("count", 0)
        batch_count += 1

    # Handle paginated S3 listings for high-volume days.
    while response.get("IsTruncated"):
        response = _s3.list_objects_v2(
            Bucket=_OUTPUT_BUCKET,
            Prefix=prefix,
            ContinuationToken=response["NextContinuationToken"],
        )
        for obj in response.get("Contents", []):
            data = _s3.get_object(Bucket=_OUTPUT_BUCKET, Key=obj["Key"])
            body = json.loads(data["Body"].read())
            total_transactions += body.get("count", 0)
            batch_count += 1

    # Write daily aggregate.
    agg_key = f"banking/aggregated/{date_prefix}/daily-summary.json"
    summary = {
        "date": date_prefix,
        "batch_count": batch_count,
        "total_transactions": total_transactions,
        "aggregated_at": now.isoformat(),
    }
    _s3.put_object(
        Bucket=_OUTPUT_BUCKET,
        Key=agg_key,
        Body=json.dumps(summary),
        ContentType="application/json",
    )

    logger.info(
        "banking-aggregator: %s -- %d batches, %d transactions",
        date_prefix,
        batch_count,
        total_transactions,
    )

    return {
        "statusCode": 200,
        "body": json.dumps(summary),
    }
