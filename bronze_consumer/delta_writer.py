import os
from datetime import datetime

import pyarrow as pa
from deltalake import write_deltalake

_BUCKET = os.environ.get("S3_BUCKET", "")

CDR_SCHEMA = pa.schema([
    ("phone_hash_out", pa.string()),
    ("phone_hash_in", pa.string()),
    ("cell_tower", pa.string()),
    ("time", pa.timestamp("us", tz="UTC")),
    ("par_day", pa.string()),
    ("par_hour", pa.string()),
])

SEQ_SCHEMA = pa.schema([
    ("phone_hash", pa.string()),
    ("cell_tower", pa.string()),
    ("host_name", pa.string()),
    ("site_name", pa.string()),
    ("time", pa.timestamp("us", tz="UTC")),
    ("par_day", pa.string()),
    ("par_hour", pa.string()),
])


def _parse_time(ts_str: str) -> datetime:
    """Parse ISO8601 timestamp string (2026-03-01T14:30:00Z)."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def write_bronze_cdr(
    records: list[dict],
    phone_hashes: dict[str, str],
    bucket: str,
    par_day: str,
    par_hour: str,
) -> int:
    """Write CDR records as a partitioned Delta Lake table at bronze/cdr/."""
    if not records:
        return 0

    rows = [{
        "phone_hash_out": phone_hashes[rec["phone_out"]],
        "phone_hash_in": phone_hashes[rec["phone_in"]],
        "cell_tower": rec["cell_tower"],
        "time": _parse_time(rec["time"]),
        "par_day": par_day,
        "par_hour": par_hour,
    } for rec in records]

    table = pa.Table.from_pylist(rows, schema=CDR_SCHEMA)
    uri = f"s3://{bucket}/bronze/cdr"
    write_deltalake(uri, table, mode="append", partition_by=["par_day", "par_hour"])
    return len(rows)


def write_bronze_seq(
    records: list[dict],
    phone_hashes: dict[str, str],
    bucket: str,
    par_day: str,
    par_hour: str,
) -> int:
    """Write SEQ records as a partitioned Delta Lake table at bronze/seq/."""
    if not records:
        return 0

    rows = [{
        "phone_hash": phone_hashes[rec["phone_number"]],
        "cell_tower": rec["cell_tower"],
        "host_name": rec["host_name"],
        "site_name": rec["site_name"],
        "time": _parse_time(rec["time"]),
        "par_day": par_day,
        "par_hour": par_hour,
    } for rec in records]

    table = pa.Table.from_pylist(rows, schema=SEQ_SCHEMA)
    uri = f"s3://{bucket}/bronze/seq"
    write_deltalake(uri, table, mode="append", partition_by=["par_day", "par_hour"])
    return len(rows)
