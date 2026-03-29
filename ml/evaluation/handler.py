"""ML evaluation Lambda.

Reads a model artifact from S3, validates metrics against quality gates,
and updates the eval_status sensor. Checks: accuracy >= 0.95, loss < 0.1,
no NaN values, weights_hash is present.
"""

import json
import logging
import math
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
_PIPELINE_ID = os.environ.get("PIPELINE_ID", "ml-evaluation")

_MIN_ACCURACY = 0.95
_MAX_LOSS = 0.1


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

    logger.info("ml-evaluation: updated sensor %s%s", sensor_key, sensor_suffix)


def _read_model_artifact(model_path: str) -> dict:
    """Read model artifact JSON from S3."""
    response = _s3.get_object(Bucket=_S3_BUCKET, Key=model_path)
    body = response["Body"].read().decode("utf-8")
    return json.loads(body)


def _is_nan(value: object) -> bool:
    """Check if a value is NaN (handles string 'NaN' from chaos injection)."""
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.lower() == "nan":
        return True
    return False


def _validate_model(artifact: dict) -> tuple[bool, str]:
    """Validate model artifact against quality gates.

    Returns (passed, reason).
    """
    # Check for NaN in any numeric field.
    for field in ("accuracy", "loss"):
        value = artifact.get(field)
        if value is None:
            return False, f"missing required field: {field}"
        if _is_nan(value):
            return False, f"NaN detected in {field}"

    accuracy = float(artifact["accuracy"])
    loss = float(artifact["loss"])

    if accuracy < _MIN_ACCURACY:
        return False, f"accuracy {accuracy:.4f} below threshold {_MIN_ACCURACY}"

    if loss >= _MAX_LOSS:
        return False, f"loss {loss:.4f} exceeds threshold {_MAX_LOSS}"

    if not artifact.get("weights_hash"):
        return False, "missing weights_hash"

    return True, "all checks passed"


def lambda_handler(event: dict, context: object) -> dict:
    """Evaluate model artifact and update eval_status sensor."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    par_day = event.get("par_day") or now.strftime("%Y%m%d")
    date_str = par_day

    model_path = f"ml/models/model_{date_str}.json"

    try:
        artifact = _read_model_artifact(model_path)
        passed, reason = _validate_model(artifact)

        accuracy_val = artifact.get("accuracy")
        loss_val = artifact.get("loss")

        # Handle NaN values for sensor writing.
        accuracy_str = "0" if accuracy_val is None or _is_nan(accuracy_val) else str(accuracy_val)
        loss_str = "0" if loss_val is None or _is_nan(loss_val) else str(loss_val)

        try:
            _write_sensor(
                sensor_key="eval_status",
                par_day=par_day,
                metadata={
                    "passed": {"BOOL": passed},
                    "accuracy": {"N": accuracy_str},
                    "loss": {"N": loss_str},
                    "reason": {"S": reason},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-evaluation: sensor write failed", exc_info=True)

        logger.info(
            "ml-evaluation: passed=%s, reason=%s, accuracy=%s, loss=%s",
            passed,
            reason,
            accuracy_str,
            loss_str,
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "passed": passed,
                "reason": reason,
                "accuracy": float(accuracy_val) if accuracy_val is not None else None,
                "loss": float(loss_val) if loss_val is not None else None,
            }),
        }

    except botocore.exceptions.ClientError as exc:
        logger.error("ml-evaluation: AWS error -- %s", exc)

        try:
            _write_sensor(
                sensor_key="eval_status",
                par_day=par_day,
                metadata={
                    "passed": {"BOOL": False},
                    "reason": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-evaluation: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "passed": False,
                "reason": str(exc),
            }),
        }

    except Exception as exc:
        logger.error("ml-evaluation: failed -- %s", exc)

        try:
            _write_sensor(
                sensor_key="eval_status",
                par_day=par_day,
                metadata={
                    "passed": {"BOOL": False},
                    "reason": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-evaluation: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "passed": False,
                "reason": str(exc),
            }),
        }
