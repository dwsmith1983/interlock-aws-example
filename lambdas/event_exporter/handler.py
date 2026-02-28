"""Event exporter Lambda: SNS subscriber that writes observability events to S3 as JSONL.

Receives batches of observability events from SNS, normalizes them, and writes
a single JSONL file per invocation to S3 staging for hourly Delta compaction.
"""

import json
import os
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]


def handler(event, context):
    lines = []
    for record in event.get("Records", []):
        sns_message = record.get("Sns", {}).get("Message", "")
        if not sns_message:
            continue
        try:
            evt = json.loads(sns_message)
        except json.JSONDecodeError:
            print(f"Skipping non-JSON SNS message: {sns_message[:200]}")
            continue

        # Normalize date field to YYYYMMDD if present
        if "date" in evt and evt["date"]:
            evt["date"] = evt["date"].replace("-", "")

        lines.append(json.dumps(evt, default=str))

    if not lines:
        print("No events to export")
        return {"exported": 0}

    now = datetime.now(timezone.utc)
    par_day = now.strftime("%Y%m%d")
    timestamp = now.strftime("%Y%m%dT%H%M%S")
    request_id = context.aws_request_id if context else "local"

    key = f"observability/staging/par_day={par_day}/{timestamp}_{request_id}.jsonl"
    body = "\n".join(lines) + "\n"

    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/x-ndjson",
    )

    print(f"Exported {len(lines)} events to s3://{BUCKET}/{key}")
    return {"exported": len(lines), "key": key}
