"""ML data preparation Lambda.

Reads raw feature CSVs from S3, cleans and normalizes the data, splits
into train/test sets (80/20), and writes prepared datasets back to S3.
Updates the data_prep_status sensor in the Interlock control table.
"""

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone

import boto3
import botocore.exceptions

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")
_dynamodb = boto3.client("dynamodb")

_S3_BUCKET = os.environ["S3_BUCKET"]
_CONTROL_TABLE = os.environ["INTERLOCK_CONTROL_TABLE"]
_PIPELINE_ID = os.environ.get("PIPELINE_ID", "ml-data-prep")

_EXPECTED_COLUMNS = [
    "age",
    "income",
    "credit_score",
    "employment_years",
    "debt_ratio",
    "num_accounts",
    "label",
]

# Normalization ranges for min-max scaling.
_NORM_RANGES: dict[str, tuple[float, float]] = {
    "age": (18.0, 80.0),
    "income": (15000.0, 150000.0),
    "credit_score": (300.0, 850.0),
    "employment_years": (0.0, 45.0),
    "debt_ratio": (0.0, 1.0),
    "num_accounts": (1.0, 15.0),
}


def _ensure_data_map(key: dict) -> None:
    """Ensure the nested data map exists on the sensor record."""
    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression="SET #data = if_not_exists(#data, :empty_map)",
        ExpressionAttributeNames={"#data": "data"},
        ExpressionAttributeValues={":empty_map": {"M": {}}},
    )


def _write_sensor(
    sensor_key: str,
    par_day: str,
    metadata: dict[str, dict],
    now_iso: str,
) -> None:
    """Write a sensor record to the Interlock control table."""
    sensor_suffix = f"#{par_day}"
    key = {
        "PK": {"S": f"PIPELINE#{_PIPELINE_ID}"},
        "SK": {"S": f"SENSOR#{sensor_key}{sensor_suffix}"},
    }

    _ensure_data_map(key)

    set_parts = ["#data.updatedAt = :now"]
    attr_names: dict[str, str] = {"#data": "data"}
    attr_values: dict[str, dict] = {":now": {"S": now_iso}}

    for field_name, field_value in metadata.items():
        placeholder = f"#{field_name}"
        value_placeholder = f":{field_name}"
        attr_names[placeholder] = field_name
        attr_values[value_placeholder] = field_value
        set_parts.append(f"#data.{placeholder} = {value_placeholder}")

    update_expr = "SET " + ", ".join(set_parts)

    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=key,
        UpdateExpression=update_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )

    logger.info("ml-data-prep: updated sensor %s%s", sensor_key, sensor_suffix)


def _read_csv_from_s3(s3_key: str) -> list[dict]:
    """Read a CSV file from S3 and return rows as dicts."""
    response = _s3.get_object(Bucket=_S3_BUCKET, Key=s3_key)
    body = response["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(body))
    return list(reader)


def _validate_columns(rows: list[dict]) -> None:
    """Validate that expected columns are present."""
    if not rows:
        raise ValueError("Empty dataset")
    actual_columns = set(rows[0].keys())
    missing = set(_EXPECTED_COLUMNS) - actual_columns
    if missing:
        raise ValueError(f"Missing expected columns: {sorted(missing)}")


def _normalize_row(row: dict) -> dict:
    """Apply min-max normalization to feature columns.

    Returns a new dict -- does not mutate the input row.
    """
    normalized = {}
    for col in _EXPECTED_COLUMNS:
        value = float(row[col])
        if col in _NORM_RANGES:
            lo, hi = _NORM_RANGES[col]
            normalized[col] = round((value - lo) / (hi - lo), 6) if hi > lo else 0.0
        else:
            normalized[col] = value
    return normalized


def _split_train_test(
    rows: list[dict],
    train_ratio: float = 0.8,
) -> tuple[list[dict], list[dict]]:
    """Split rows into train and test sets deterministically."""
    split_idx = int(len(rows) * train_ratio)
    return rows[:split_idx], rows[split_idx:]


def _write_csv_to_s3(rows: list[dict], s3_key: str) -> None:
    """Write rows as CSV to S3."""
    if not rows:
        return
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    _s3.put_object(
        Bucket=_S3_BUCKET,
        Key=s3_key,
        Body=output.getvalue().encode("utf-8"),
        ContentType="text/csv",
    )


def lambda_handler(event: dict, context: object) -> dict:
    """Read raw features, normalize, split, and write prepared datasets."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    par_day = event.get("par_day") or now.strftime("%Y%m%d")
    date_str = par_day

    raw_key = f"ml/raw/features_{date_str}.csv"

    try:
        rows = _read_csv_from_s3(raw_key)
        _validate_columns(rows)

        normalized = [_normalize_row(r) for r in rows]
        train_set, test_set = _split_train_test(normalized)

        train_key = f"ml/prepared/train_{date_str}.csv"
        test_key = f"ml/prepared/test_{date_str}.csv"

        _write_csv_to_s3(train_set, train_key)
        _write_csv_to_s3(test_set, test_key)

        feature_count = len(_EXPECTED_COLUMNS) - 1  # Exclude label

        try:
            _write_sensor(
                sensor_key="data_prep_status",
                par_day=par_day,
                metadata={
                    "complete": {"BOOL": True},
                    "row_count": {"N": str(len(rows))},
                    "feature_count": {"N": str(feature_count)},
                    "train_rows": {"N": str(len(train_set))},
                    "test_rows": {"N": str(len(test_set))},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-data-prep: sensor write failed", exc_info=True)

        logger.info(
            "ml-data-prep: prepared %d rows (%d train, %d test), %d features",
            len(rows),
            len(train_set),
            len(test_set),
            feature_count,
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "complete": True,
                "row_count": len(rows),
                "feature_count": feature_count,
                "train_rows": len(train_set),
                "test_rows": len(test_set),
            }),
        }

    except botocore.exceptions.ClientError as exc:
        logger.error("ml-data-prep: AWS error -- %s", exc)

        try:
            _write_sensor(
                sensor_key="data_prep_status",
                par_day=par_day,
                metadata={
                    "complete": {"BOOL": False},
                    "error": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-data-prep: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "complete": False,
                "error": str(exc),
            }),
        }

    except Exception as exc:
        logger.error("ml-data-prep: failed -- %s", exc)

        try:
            _write_sensor(
                sensor_key="data_prep_status",
                par_day=par_day,
                metadata={
                    "complete": {"BOOL": False},
                    "error": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-data-prep: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "complete": False,
                "error": str(exc),
            }),
        }
