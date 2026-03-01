import os
from datetime import datetime, timezone

from generator.distribution import floor_to_window
from generator.generate import generate_and_upload


def lambda_handler(event: dict, context) -> dict:
    stream: str = event["stream"]
    daily_target: int = event["daily_target"]

    now = datetime.now(timezone.utc)
    window_start = floor_to_window(now)

    bucket = os.environ.get("S3_BUCKET", "telecom-data-local")

    summary = generate_and_upload(stream, window_start, daily_target, bucket)
    print(summary)
    return summary
