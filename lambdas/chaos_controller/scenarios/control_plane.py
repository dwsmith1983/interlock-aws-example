"""Category 3: Control Plane Chaos — DynamoDB state manipulation.

Scenarios:
- cas-conflict: Force CAS conflict by bumping RunState version
"""

import json
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

ddb = boto3.client("dynamodb")


def cas_conflict(ctx):
    """Force CAS conflict by bumping the top-level version on an active run's truth item.

    The interlock framework stores run truth at PK=RUN#{runID}, SK=RUN#{runID}
    with a top-level numeric ``version`` attribute.  CompareAndSwapRunState checks
    this via ``ConditionExpression "#version = :expectedVersion"``.  Bumping the
    version by +10 guarantees the next CAS attempt will fail and trigger a retry.
    """
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]

    # Step 1: Find recent runs via the pipeline's run list copies
    pk = f"PIPELINE#{pipeline_id}"
    try:
        resp = ddb.query(
            TableName=table,
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": pk},
                ":prefix": {"S": "RUN#"},
            },
            ScanIndexForward=False,
            Limit=10,
        )
    except ClientError:
        logger.exception("error querying runs for %s", pipeline_id)
        return {"skipped": True, "reason": "error querying runs"}

    # Step 2: Find an active (non-terminal) run
    non_terminal = {"PENDING", "TRIGGERING", "RUNNING", "COMPLETED_MONITORING"}
    run_id = None
    for item in resp.get("Items", []):
        data_str = item.get("data", {}).get("S", "{}")
        try:
            data = json.loads(data_str)
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("status") in non_terminal:
            run_id = data.get("runId") or data.get("runID")
            break

    if not run_id:
        return {"skipped": True, "reason": "no active run"}

    # Step 3: Read the truth item with consistent read
    truth_pk = f"RUN#{run_id}"
    truth_sk = f"RUN#{run_id}"
    try:
        truth_resp = ddb.get_item(
            TableName=table,
            Key={"PK": {"S": truth_pk}, "SK": {"S": truth_sk}},
            ConsistentRead=True,
        )
    except ClientError:
        logger.exception("error reading truth item for run %s", run_id)
        return {"skipped": True, "reason": "error reading truth item"}

    truth_item = truth_resp.get("Item")
    if not truth_item:
        return {"skipped": True, "reason": f"truth item not found for run {run_id}"}

    # Step 4: Bump the top-level version attribute
    current_version = int(truth_item.get("version", {}).get("N", "0"))
    new_version = current_version + 10

    try:
        ddb.update_item(
            TableName=table,
            Key={"PK": {"S": truth_pk}, "SK": {"S": truth_sk}},
            UpdateExpression="SET #v = :newVersion",
            ExpressionAttributeNames={"#v": "version"},
            ExpressionAttributeValues={":newVersion": {"N": str(new_version)}},
        )
    except ClientError:
        logger.exception("error bumping version for run %s", run_id)
        return {"skipped": True, "reason": "error bumping version"}

    logger.info("forced CAS conflict for %s run %s (version %d -> %d)",
                pipeline_id, run_id, current_version, new_version)
    return {
        "action": "cas_conflict",
        "pipeline": pipeline_id,
        "runId": run_id,
        "oldVersion": current_version,
        "newVersion": new_version,
    }
