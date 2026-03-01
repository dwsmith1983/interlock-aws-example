import os
from datetime import datetime

import pyarrow as pa
from deltalake import write_deltalake

_BUCKET = os.environ.get("S3_BUCKET", "")

CDR_SCHEMA = pa.schema([
    ("phone_hash_out", pa.string()),
    ("phone_hash_in", pa.string()),
    ("cell_tower", pa.string()),
    ("time", pa.timestamp("us")),
])

SEQ_SCHEMA = pa.schema([
    ("phone_hash", pa.string()),
    ("cell_tower", pa.string()),
    ("host_name", pa.string()),
    ("site_name", pa.string()),
    ("time", pa.timestamp("us")),
])


def _parse_time(ts_str: str) -> datetime:
    """Parse ISO8601 timestamp string (2026-03-01T14:30:00Z)."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def _partition_key(dt: datetime) -> tuple[str, str]:
    """Extract par_day and par_hour from a datetime."""
    return dt.strftime("%Y%m%d"), dt.strftime("%H")


def write_bronze_cdr(
    records: list[dict],
    phone_hashes: dict[str, str],
    bucket: str | None = None,
) -> int:
    """Write CDR records as Delta Lake to bronze/cdr/, returning count written."""
    bucket = bucket or _BUCKET
    if not records:
        return 0

    # Group records by partition
    partitions: dict[tuple[str, str], list[dict]] = {}
    for rec in records:
        dt = _parse_time(rec["time"])
        key = _partition_key(dt)
        partitions.setdefault(key, []).append({
            "phone_hash_out": phone_hashes[rec["phone_out"]],
            "phone_hash_in": phone_hashes[rec["phone_in"]],
            "cell_tower": rec["cell_tower"],
            "time": dt,
        })

    total = 0
    for (par_day, par_hour), rows in partitions.items():
        table = pa.Table.from_pylist(rows, schema=CDR_SCHEMA)
        uri = f"s3://{bucket}/bronze/cdr/par_day={par_day}/par_hour={par_hour}"
        write_deltalake(uri, table, mode="append")
        total += len(rows)

    return total


def write_bronze_seq(
    records: list[dict],
    phone_hashes: dict[str, str],
    bucket: str | None = None,
) -> int:
    """Write SEQ records as Delta Lake to bronze/seq/, returning count written."""
    bucket = bucket or _BUCKET
    if not records:
        return 0

    partitions: dict[tuple[str, str], list[dict]] = {}
    for rec in records:
        dt = _parse_time(rec["time"])
        key = _partition_key(dt)
        partitions.setdefault(key, []).append({
            "phone_hash": phone_hashes[rec["phone_number"]],
            "cell_tower": rec["cell_tower"],
            "host_name": rec["host_name"],
            "site_name": rec["site_name"],
            "time": dt,
        })

    total = 0
    for (par_day, par_hour), rows in partitions.items():
        table = pa.Table.from_pylist(rows, schema=SEQ_SCHEMA)
        uri = f"s3://{bucket}/bronze/seq/par_day={par_day}/par_hour={par_hour}"
        write_deltalake(uri, table, mode="append")
        total += len(rows)

    return total
