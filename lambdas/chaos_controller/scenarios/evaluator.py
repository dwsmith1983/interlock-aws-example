"""Category 5: Evaluator Chaos — evaluation manipulation.

Scenarios:
- eval-block: Write CHAOS#BLOCK record to fail evaluator
- eval-slow: Write CHAOS#SLOW record to add artificial delay
- dup-data: Write same bronze content twice with same dedup hash
"""

import json
import logging

import boto3

logger = logging.getLogger(__name__)

ddb = boto3.client("dynamodb")
s3 = boto3.client("s3")


def eval_block(ctx):
    """Write CHAOS#BLOCK record to make evaluator return FAIL."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    ttl = int(now.timestamp()) + (15 * 60)  # 15 minute TTL

    ddb.put_item(
        TableName=table,
        Item={
            "PK": {"S": f"CHAOS#BLOCK#{pipeline_id}"},
            "SK": {"S": "ACTIVE"},
            "injectedAt": {"S": now.isoformat()},
            "ttl": {"N": str(ttl)},
        },
    )
    logger.info("wrote eval-block for %s (expires in 15m)", pipeline_id)
    return {"action": "eval_block", "pipeline": pipeline_id, "ttlMinutes": 15}


def eval_slow(ctx):
    """Write CHAOS#SLOW record to add artificial 25s delay to evaluator."""
    table = ctx["table_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    ttl = int(now.timestamp()) + (15 * 60)

    ddb.put_item(
        TableName=table,
        Item={
            "PK": {"S": f"CHAOS#SLOW#{pipeline_id}"},
            "SK": {"S": "ACTIVE"},
            "delaySeconds": {"N": "25"},
            "injectedAt": {"S": now.isoformat()},
            "ttl": {"N": str(ttl)},
        },
    )
    logger.info("wrote eval-slow for %s (25s delay, expires in 15m)", pipeline_id)
    return {"action": "eval_slow", "pipeline": pipeline_id, "delaySeconds": 25, "ttlMinutes": 15}


def dup_data(ctx):
    """Write same bronze content twice with same dedup hash to test dedup."""
    table = ctx["table_name"]
    bucket = ctx["bucket_name"]
    pipeline_id = ctx["pipeline_id"]
    now = ctx["now"]
    par_day = now.strftime("%Y%m%d")
    par_hour = now.strftime("%H")

    source = "earthquake" if "earthquake" in pipeline_id else "crypto"

    # Write identical content twice
    content = json.dumps({
        "chaos": True,
        "scenario": "dup-data",
        "source": source,
        "timestamp": now.isoformat(),
    }).encode()

    for i in range(2):
        key = f"bronze/{source}/par_day={par_day}/par_hour={par_hour}/chaos_dup_{i}.jsonl"
        s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/json")

    logger.info("wrote duplicate bronze data for %s", source)
    return {"action": "dup_data", "source": source, "par_day": par_day, "par_hour": par_hour}
