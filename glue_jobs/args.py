"""Glue job argument resolution with defaults for scheduled invocations."""

import sys
from datetime import datetime, timedelta, timezone

from awsglue.utils import getResolvedOptions


def resolve_args(required_keys: list[str], optional_keys: list[str] | None = None) -> dict[str, str]:
    """Resolve Glue job arguments, computing time-based defaults for scheduled runs.

    For scheduled (EventBridge) invocations, par_day and par_hour may not be provided.
    Hourly jobs default to the previous hour; daily jobs default to the previous day.
    """
    # getResolvedOptions only resolves keys present in sys.argv
    present = [k for k in (required_keys + (optional_keys or [])) if f"--{k}" in sys.argv]
    args = getResolvedOptions(sys.argv, present) if present else {}

    if "s3_bucket" not in args:
        raise ValueError("--s3_bucket is required")

    now = datetime.now(timezone.utc)

    if "par_day" not in args:
        # Default: previous day for daily jobs, today for hourly
        if "par_hour" in (optional_keys or []):
            # Hourly job: use the previous hour
            prev_hour = now - timedelta(hours=1)
            args["par_day"] = prev_hour.strftime("%Y%m%d")
        else:
            # Daily job: use previous day
            prev_day = now - timedelta(days=1)
            args["par_day"] = prev_day.strftime("%Y%m%d")

    if "par_hour" not in args and "par_hour" in (optional_keys or []):
        prev_hour = now - timedelta(hours=1)
        args["par_hour"] = prev_hour.strftime("%H")

    return args
