"""Update daily-status sensor when silver hourly jobs complete."""
import logging
import os

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_dynamodb = boto3.client("dynamodb")
_CONTROL_TABLE = os.environ["INTERLOCK_CONTROL_TABLE"]

# Map hourly pipeline -> daily pipeline
_DAILY_PIPELINE = {
    "silver-cdr-hour": "silver-cdr-day",
    "silver-seq-hour": "silver-seq-day",
}


def handler(event, context):
    """Handle JOB_COMPLETED events from silver hourly pipelines."""
    detail = event.get("detail", {})
    pipeline_id = detail.get("pipelineId", "")
    date_str = detail.get("date", "")  # e.g. "2026-03-04T23"

    daily_pipeline = _DAILY_PIPELINE.get(pipeline_id)
    if not daily_pipeline:
        logger.info(
            "Ignoring JOB_COMPLETED for %s (not a tracked hourly pipeline)",
            pipeline_id,
        )
        return

    # Extract hour from composite date (e.g. "2026-03-04T23" -> hour "23", day "2026-03-04")
    if "T" in date_str:
        par_day, par_hour = date_str.rsplit("T", 1)
    else:
        logger.warning(
            "No hour component in date %s for %s, skipping",
            date_str,
            pipeline_id,
        )
        return

    _update_daily_sensor(daily_pipeline, par_day, par_hour)


def _update_daily_sensor(daily_pipeline, par_day, par_hour):
    """Add completed hour to daily-status sensor. Trigger daily when all 24 present."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    daily_key = {
        "PK": {"S": f"PIPELINE#{daily_pipeline}"},
        "SK": {"S": f"SENSOR#daily-status#{par_day}"},
    }

    # Ensure data map exists
    _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=daily_key,
        UpdateExpression="SET #data = if_not_exists(#data, :empty_map)",
        ExpressionAttributeNames={"#data": "data"},
        ExpressionAttributeValues={":empty_map": {"M": {}}},
    )

    # Add hour to completed set
    resp = _dynamodb.update_item(
        TableName=_CONTROL_TABLE,
        Key=daily_key,
        UpdateExpression=(
            "SET #data.#date = :date, #data.updatedAt = :now "
            "ADD #data.completed_hours :hour_set"
        ),
        ExpressionAttributeNames={"#data": "data", "#date": "date"},
        ExpressionAttributeValues={
            ":date": {"S": par_day},
            ":now": {"S": now},
            ":hour_set": {"SS": [par_hour]},
        },
        ReturnValues="ALL_NEW",
    )

    attrs = resp.get("Attributes", {})
    data = attrs.get("data", {}).get("M", {})
    completed = data.get("completed_hours", {}).get("SS", [])

    if len(completed) >= 24:
        _dynamodb.update_item(
            TableName=_CONTROL_TABLE,
            Key=daily_key,
            UpdateExpression="SET #data.all_hours_complete = :complete",
            ExpressionAttributeNames={"#data": "data"},
            ExpressionAttributeValues={":complete": {"BOOL": True}},
        )
        logger.info(
            "%s %s: all 24 hours complete, daily triggered",
            daily_pipeline,
            par_day,
        )
    else:
        logger.info(
            "%s %s: %d/24 hours complete",
            daily_pipeline,
            par_day,
            len(completed),
        )
