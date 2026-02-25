"""Category 3: Control Plane Chaos — DynamoDB state manipulation.

Scenarios:
- delete-lock: Delete an active LOCK record
- corrupt-runlog: Overwrite a COMPLETED RUNLOG status to FAILED
- delete-config: Remove a PIPELINE#CONFIG record
- cas-conflict: Force CAS conflict by bumping RunState version
- corrupt-runlog-json: Write invalid JSON in RUNLOG data field
"""

import json
import logging
import random
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

ddb = boto3.client("dynamodb")


def delete_lock(ctx):
    """Find and delete a LOCK record for a running pipeline."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]

    # Scan for LOCK records
    try:
        resp = ddb.query(
            TableName=table,
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
            ExpressionAttributeValues={
                ":pk": {"S": f"LOCK#{pipeline_id}"},
                ":sk": {"S": "LOCK#"},
            },
            Limit=5,
        )
        items = resp.get("Items", [])
        if not items:
            # Try without pipeline-scoped lock key pattern
            resp = ddb.query(
                TableName=table,
                KeyConditionExpression="PK = :pk",
                ExpressionAttributeValues={
                    ":pk": {"S": f"LOCK#{pipeline_id}"},
                },
                Limit=5,
            )
            items = resp.get("Items", [])

        if not items:
            return {"skipped": True, "reason": f"no lock found for {pipeline_id}"}

        item = random.choice(items)
        pk = item["PK"]["S"]
        sk = item["SK"]["S"]

        ddb.delete_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        logger.info("deleted lock: PK=%s SK=%s", pk, sk)
        return {"action": "deleted_lock", "pk": pk, "sk": sk}
    except ClientError:
        logger.exception("error deleting lock for %s", pipeline_id)
        return {"skipped": True, "reason": "error"}


def corrupt_runlog(ctx):
    """Overwrite a COMPLETED RUNLOG status to FAILED."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    date = now.strftime("%Y%m%d")
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    pk = f"PIPELINE#{pipeline_id}"
    sk = f"RUNLOG#{date}#{schedule_id}"

    try:
        resp = ddb.get_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        item = resp.get("Item")
        if not item:
            return {"skipped": True, "reason": f"no RUNLOG for {pipeline_id}/{schedule_id}"}

        data = json.loads(item.get("data", {}).get("S", "{}"))
        if data.get("status") != "COMPLETED":
            return {"skipped": True, "reason": f"RUNLOG status is {data.get('status')}, not COMPLETED"}

        # Corrupt: change status to FAILED
        data["status"] = "FAILED"
        data["chaosCorrupted"] = True
        ddb.update_item(
            TableName=table,
            Key={"PK": {"S": pk}, "SK": {"S": sk}},
            UpdateExpression="SET #d = :data",
            ExpressionAttributeNames={"#d": "data"},
            ExpressionAttributeValues={":data": {"S": json.dumps(data)}},
        )
        logger.info("corrupted RUNLOG for %s/%s: COMPLETED -> FAILED", pipeline_id, schedule_id)
        return {"action": "corrupted_runlog", "pipeline": pipeline_id, "schedule": schedule_id}
    except ClientError:
        logger.exception("error corrupting runlog for %s", pipeline_id)
        return {"skipped": True, "reason": "error"}


def delete_config(ctx):
    """Remove a PIPELINE#CONFIG record."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]

    pk = f"PIPELINE#{pipeline_id}"
    sk = "CONFIG"

    try:
        # Save backup before deleting
        resp = ddb.get_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        if "Item" not in resp:
            return {"skipped": True, "reason": f"no CONFIG for {pipeline_id}"}

        # Store backup as chaos record
        backup_data = json.dumps({k: _attr_to_val(v) for k, v in resp["Item"].items()})

        ddb.delete_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        logger.info("deleted CONFIG for %s", pipeline_id)
        return {"action": "deleted_config", "pipeline": pipeline_id, "backup": backup_data}
    except ClientError:
        logger.exception("error deleting config for %s", pipeline_id)
        return {"skipped": True, "reason": "error"}


def cas_conflict(ctx):
    """Force CAS conflict by writing RunState with incremented version."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    date = now.strftime("%Y%m%d")
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    pk = f"PIPELINE#{pipeline_id}"
    sk = f"RUNSTATE#{date}#{schedule_id}"

    try:
        resp = ddb.get_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        item = resp.get("Item")

        if item:
            # Increment version to force CAS conflict on next write
            data = json.loads(item.get("data", {}).get("S", "{}"))
            version = data.get("version", 0) + 10
            data["version"] = version
            data["chaosConflict"] = True
            ddb.update_item(
                TableName=table,
                Key={"PK": {"S": pk}, "SK": {"S": sk}},
                UpdateExpression="SET #d = :data",
                ExpressionAttributeNames={"#d": "data"},
                ExpressionAttributeValues={":data": {"S": json.dumps(data)}},
            )
            logger.info("forced CAS conflict for %s/%s (version=%d)", pipeline_id, schedule_id, version)
            return {"action": "cas_conflict", "pipeline": pipeline_id, "version": version}
        else:
            # Create a RunState with high version number
            data = {"version": 999, "chaosConflict": True, "status": "CONFLICT"}
            ttl = int(now.timestamp()) + 86400
            ddb.put_item(
                TableName=table,
                Item={
                    "PK": {"S": pk},
                    "SK": {"S": sk},
                    "data": {"S": json.dumps(data)},
                    "ttl": {"N": str(ttl)},
                },
            )
            logger.info("created conflicting RunState for %s/%s", pipeline_id, schedule_id)
            return {"action": "cas_conflict_created", "pipeline": pipeline_id, "version": 999}
    except ClientError:
        logger.exception("error creating CAS conflict for %s", pipeline_id)
        return {"skipped": True, "reason": "error"}


def corrupt_runlog_json(ctx):
    """Write invalid JSON in RUNLOG data field."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    date = now.strftime("%Y%m%d")
    hour = now.strftime("%H")
    schedule_id = f"h{hour}"

    pk = f"PIPELINE#{pipeline_id}"
    sk = f"RUNLOG#{date}#{schedule_id}"

    try:
        resp = ddb.get_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        if "Item" not in resp:
            return {"skipped": True, "reason": f"no RUNLOG for {pipeline_id}/{schedule_id}"}

        invalid_json = '{"status": "COMPLETED", "chaosCorrupted": tru'  # Truncated JSON
        ddb.update_item(
            TableName=table,
            Key={"PK": {"S": pk}, "SK": {"S": sk}},
            UpdateExpression="SET #d = :data",
            ExpressionAttributeNames={"#d": "data"},
            ExpressionAttributeValues={":data": {"S": invalid_json}},
        )
        logger.info("corrupted RUNLOG JSON for %s/%s", pipeline_id, schedule_id)
        return {"action": "corrupted_runlog_json", "pipeline": pipeline_id, "schedule": schedule_id}
    except ClientError:
        logger.exception("error corrupting runlog JSON for %s", pipeline_id)
        return {"skipped": True, "reason": "error"}


def _attr_to_val(attr):
    """Convert DynamoDB attribute to Python value (simplified)."""
    if "S" in attr:
        return attr["S"]
    if "N" in attr:
        return attr["N"]
    if "BOOL" in attr:
        return attr["BOOL"]
    return str(attr)
