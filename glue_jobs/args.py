"""Glue job argument resolution with defaults for scheduled invocations."""

import sys
from datetime import datetime, timedelta, timezone

from awsglue.utils import getResolvedOptions


def resolve_args(required_keys: list[str], optional_keys: list[str] | None = None) -> dict[str, str]:
    """Resolve Glue job arguments, computing time-based defaults.

    Hourly jobs: if minute >= 45 use current hour (sensor-triggered at ~:48-50),
    otherwise use previous hour (cron/manual at :05). Daily jobs: previous day.
    """
    # getResolvedOptions only resolves keys present in sys.argv
    present = [k for k in (required_keys + (optional_keys or [])) if f"--{k}" in sys.argv]
    args = getResolvedOptions(sys.argv, present) if present else {}

    if "s3_bucket" not in args:
        raise ValueError("--s3_bucket is required")

    now = datetime.now(timezone.utc)

    if "par_day" not in args:
        if "par_hour" in (optional_keys or []):
            # Hourly job: use current hour if past :45 (sensor-triggered),
            # otherwise previous hour (cron/manual at :05)
            if now.minute >= 45:
                args["par_day"] = now.strftime("%Y%m%d")
            else:
                prev_hour = now - timedelta(hours=1)
                args["par_day"] = prev_hour.strftime("%Y%m%d")
        else:
            # Daily job: use previous day
            prev_day = now - timedelta(days=1)
            args["par_day"] = prev_day.strftime("%Y%m%d")

    if "par_hour" not in args and "par_hour" in (optional_keys or []):
        if now.minute >= 45:
            args["par_hour"] = now.strftime("%H")
        else:
            prev_hour = now - timedelta(hours=1)
            args["par_hour"] = prev_hour.strftime("%H")

    return args
