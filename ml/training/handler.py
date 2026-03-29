"""ML training Lambda.

Mock model training. Reads prepared features from S3, generates a
deterministic model artifact with accuracy, loss, epochs, and weights_hash.
Writes the model artifact to S3 and updates the training_status sensor.
"""

import hashlib
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
_PIPELINE_ID = os.environ.get("PIPELINE_ID", "ml-training")


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

    logger.info("ml-training: updated sensor %s%s", sensor_key, sensor_suffix)


def _read_training_data(date_str: str) -> str:
    """Read training CSV from S3 and return raw content for hashing."""
    train_key = f"ml/prepared/train_{date_str}.csv"
    response = _s3.get_object(Bucket=_S3_BUCKET, Key=train_key)
    return response["Body"].read().decode("utf-8")


def _train_model(training_data: str, date_str: str, trained_at: str) -> dict:
    """Mock model training -- returns a deterministic model artifact.

    The weights_hash is derived from the training data content, making
    the model deterministic for the same input.
    """
    weights_hash = hashlib.sha256(training_data.encode("utf-8")).hexdigest()

    row_count = training_data.count("\n") - 1  # Subtract header

    # Deterministic metrics based on data hash.
    hash_int = int(weights_hash[:8], 16)
    accuracy = 0.95 + (hash_int % 300) / 10000  # 0.95 -- 0.98
    loss = 0.01 + (hash_int % 200) / 10000       # 0.01 -- 0.03

    return {
        "model_version": f"v1.0.{date_str}",
        "accuracy": round(accuracy, 4),
        "loss": round(loss, 4),
        "epochs": 50,
        "training_rows": row_count,
        "weights_hash": weights_hash,
        "trained_at": trained_at,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """Train model and write artifact to S3."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    par_day = event.get("par_day") or now.strftime("%Y%m%d")
    date_str = par_day

    try:
        training_data = _read_training_data(date_str)
        model_artifact = _train_model(training_data, date_str, trained_at=now_iso)

        model_key = f"ml/models/model_{date_str}.json"
        _s3.put_object(
            Bucket=_S3_BUCKET,
            Key=model_key,
            Body=json.dumps(model_artifact).encode("utf-8"),
            ContentType="application/json",
        )

        try:
            _write_sensor(
                sensor_key="training_status",
                par_day=par_day,
                metadata={
                    "complete": {"BOOL": True},
                    "accuracy": {"N": str(model_artifact["accuracy"])},
                    "loss": {"N": str(model_artifact["loss"])},
                    "model_path": {"S": model_key},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-training: sensor write failed", exc_info=True)

        logger.info(
            "ml-training: model trained -- accuracy=%.4f, loss=%.4f, path=%s",
            model_artifact["accuracy"],
            model_artifact["loss"],
            model_key,
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "complete": True,
                "model_path": model_key,
                "accuracy": model_artifact["accuracy"],
                "loss": model_artifact["loss"],
            }),
        }

    except botocore.exceptions.ClientError as exc:
        logger.error("ml-training: AWS error -- %s", exc)

        try:
            _write_sensor(
                sensor_key="training_status",
                par_day=par_day,
                metadata={
                    "complete": {"BOOL": False},
                    "error": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-training: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "complete": False,
                "error": str(exc),
            }),
        }

    except Exception as exc:
        logger.error("ml-training: failed -- %s", exc)

        try:
            _write_sensor(
                sensor_key="training_status",
                par_day=par_day,
                metadata={
                    "complete": {"BOOL": False},
                    "error": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-training: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "complete": False,
                "error": str(exc),
            }),
        }
