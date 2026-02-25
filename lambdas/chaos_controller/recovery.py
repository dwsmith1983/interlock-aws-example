"""Recovery checker: Queries INJECTED/DETECTED chaos events and checks for recovery.

Runs every chaos-controller cycle. For each unresolved chaos event:
1. Check if the target pipeline has a successful RUNLOG after injection time
2. If yes: update status to RECOVERED
3. If recovery timeout exceeded: update to UNRECOVERED (finding!)
"""

import json
import logging
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

ddb = boto3.client("dynamodb")


def check_recovery(table_name, now):
    """Check all INJECTED/DETECTED chaos events for recovery.

    Returns (recovered_count, unrecovered_count).
    """
    recovered = 0
    unrecovered = 0

    events = _query_unresolved_events(table_name)
    for event in events:
        scenario = event.get("scenario", {}).get("S", "")
        target = event.get("target", {}).get("S", "")
        injected_at_str = event.get("injectedAt", {}).get("S", "")
        timeout_minutes = int(event.get("recoveryTimeoutMinutes", {}).get("N", "60"))
        status = event.get("status", {}).get("S", "")
        pk = event["PK"]["S"]
        sk = event["SK"]["S"]

        if not injected_at_str:
            continue

        try:
            injected_at = datetime.fromisoformat(injected_at_str)
        except ValueError:
            continue

        # Check if recovery timeout exceeded
        if now > injected_at + timedelta(minutes=timeout_minutes):
            _update_status(table_name, pk, sk, "UNRECOVERED", now)
            unrecovered += 1
            logger.warning("UNRECOVERED chaos event: %s on %s (injected %s, timeout %dm)",
                           scenario, target, injected_at_str, timeout_minutes)
            continue

        # Check for successful RUNLOG after injection time
        if _has_recovered(table_name, target, injected_at):
            _update_status(table_name, pk, sk, "RECOVERED", now)
            recovered += 1
            logger.info("RECOVERED chaos event: %s on %s", scenario, target)

    return recovered, unrecovered


def _query_unresolved_events(table_name):
    """Query all CHAOS# events with status INJECTED or DETECTED."""
    events = []
    try:
        resp = ddb.query(
            TableName=table_name,
            KeyConditionExpression="PK = :pk",
            FilterExpression="#s IN (:s1, :s2)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":pk": {"S": "CHAOS#EVENTS"},
                ":s1": {"S": "INJECTED"},
                ":s2": {"S": "DETECTED"},
            },
            ScanIndexForward=False,
            Limit=100,
        )
        events = resp.get("Items", [])
    except ClientError:
        logger.exception("error querying unresolved chaos events")
    return events


def _has_recovered(table_name, target, injected_at):
    """Check if the target pipeline has a successful RUNLOG after injection time."""
    pk = f"PIPELINE#{target}"
    try:
        resp = ddb.query(
            TableName=table_name,
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": pk},
                ":prefix": {"S": "RUNLOG#"},
            },
            ScanIndexForward=False,
            Limit=10,
        )
        for item in resp.get("Items", []):
            data_str = item.get("data", {}).get("S", "{}")
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning("skipping RUNLOG with corrupt JSON for %s: %s", target, data_str[:200])
                continue
            if data.get("status") == "COMPLETED":
                completed_at_str = data.get("completedAt", "")
                if completed_at_str:
                    try:
                        completed_at = datetime.fromisoformat(completed_at_str)
                        if completed_at > injected_at:
                            return True
                    except ValueError:
                        pass
                else:
                    # If no completedAt, check the SK timestamp
                    return True
    except ClientError:
        logger.exception("error checking recovery for %s", target)
    return False


def _update_status(table_name, pk, sk, new_status, now):
    """Update the status of a chaos event."""
    try:
        update_expr = "SET #s = :status"
        expr_values = {":status": {"S": new_status}}
        expr_names = {"#s": "status"}

        if new_status == "RECOVERED":
            update_expr += ", recoveredAt = :ts"
            expr_values[":ts"] = {"S": now.isoformat()}
        elif new_status == "UNRECOVERED":
            update_expr += ", unrecoveredAt = :ts"
            expr_values[":ts"] = {"S": now.isoformat()}

        ddb.update_item(
            TableName=table_name,
            Key={"PK": {"S": pk}, "SK": {"S": sk}},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
    except ClientError:
        logger.exception("error updating chaos event status")
