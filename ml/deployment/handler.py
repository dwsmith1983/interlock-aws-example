"""ML deployment Lambda.

Copies a validated model artifact from ml/models/ to ml/production/
and updates the deployment_status sensor. Only runs when evaluation
has passed (enforced by interlock trigger).
"""

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
_PIPELINE_ID = os.environ.get("PIPELINE_ID", "ml-deployment")


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

    logger.info("ml-deployment: updated sensor %s%s", sensor_key, sensor_suffix)


def lambda_handler(event: dict, context: object) -> dict:
    """Copy validated model to production and update deployment sensor."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    par_day = event.get("par_day") or now.strftime("%Y%m%d")
    date_str = par_day

    source_key = f"ml/models/model_{date_str}.json"
    dest_key = f"ml/production/model_{date_str}.json"

    try:
        _s3.copy_object(
            Bucket=_S3_BUCKET,
            CopySource={"Bucket": _S3_BUCKET, "Key": source_key},
            Key=dest_key,
        )

        try:
            _write_sensor(
                sensor_key="deployment_status",
                par_day=par_day,
                metadata={
                    "deployed": {"BOOL": True},
                    "model_path": {"S": dest_key},
                    "source_path": {"S": source_key},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-deployment: sensor write failed", exc_info=True)

        logger.info(
            "ml-deployment: deployed model %s -> %s",
            source_key,
            dest_key,
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "deployed": True,
                "model_path": dest_key,
            }),
        }

    except botocore.exceptions.ClientError as exc:
        logger.error("ml-deployment: AWS error -- %s", exc)

        try:
            _write_sensor(
                sensor_key="deployment_status",
                par_day=par_day,
                metadata={
                    "deployed": {"BOOL": False},
                    "error": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-deployment: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "deployed": False,
                "error": str(exc),
            }),
        }

    except Exception as exc:
        logger.error("ml-deployment: failed -- %s", exc)

        try:
            _write_sensor(
                sensor_key="deployment_status",
                par_day=par_day,
                metadata={
                    "deployed": {"BOOL": False},
                    "error": {"S": str(exc)},
                },
                now_iso=now_iso,
            )
        except botocore.exceptions.ClientError:
            logger.error("ml-deployment: sensor write failed", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "deployed": False,
                "error": str(exc),
            }),
        }
