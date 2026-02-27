"""Category 3: Control Plane Chaos — DynamoDB state manipulation.

Scenarios:
- cas-conflict: Force CAS conflict by bumping RunState version
"""

import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

ddb = boto3.client("dynamodb")


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
