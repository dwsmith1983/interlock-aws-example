"""Chaos Controller: Probabilistically injects real failures across 5 categories.

Triggered every 20 minutes by EventBridge (gated by chaos_enabled Terraform variable).
Reads chaos config from DynamoDB, applies severity gating and cooldown enforcement,
probabilistically selects scenarios, injects failures, and tracks recovery.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

from scenarios import infrastructure, data_plane, control_plane, cascade, evaluator
from recovery import check_recovery

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ddb = boto3.client("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "medallion-interlock")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")

# Scenario registry: maps scenario ID to (module, function)
SCENARIO_REGISTRY = {
    # Category 1: Infrastructure
    "sfn-kill": infrastructure.sfn_kill,
    "lambda-throttle": infrastructure.lambda_throttle,
    "lambda-throttle-ingest": infrastructure.lambda_throttle_ingest,
    # Category 2: Data plane
    "delete-bronze": data_plane.delete_bronze,
    "corrupt-bronze": data_plane.corrupt_bronze,
    "empty-bronze": data_plane.empty_bronze,
    "corrupt-delta-log": data_plane.corrupt_delta_log,
    "wrong-partition": data_plane.wrong_partition,
    # Category 3: Control plane
    "delete-lock": control_plane.delete_lock,
    "corrupt-runlog": control_plane.corrupt_runlog,
    "delete-config": control_plane.delete_config,
    "cas-conflict": control_plane.cas_conflict,
    "corrupt-runlog-json": control_plane.corrupt_runlog_json,
    # Category 4: Cascade
    "dup-marker": cascade.dup_marker,
    "burst-markers": cascade.burst_markers,
    "future-marker": cascade.future_marker,
    "late-data": cascade.late_data,
    "delete-upstream-runlog": cascade.delete_upstream_runlog,
    "orphan-marker": cascade.orphan_marker,
    # Category 5: Evaluator
    "eval-block": evaluator.eval_block,
    "eval-slow": evaluator.eval_slow,
    "eval-false-pass": evaluator.eval_false_pass,
    "dup-data": evaluator.dup_data,
}

SEVERITY_ORDER = {"mild": 0, "moderate": 1, "severe": 2}

PIPELINES = ["earthquake-silver", "earthquake-gold", "crypto-silver", "crypto-gold"]


def handler(event, context):
    """Main chaos controller entry point."""
    now = datetime.now(timezone.utc)
    logger.info("chaos-controller invoked at %s", now.isoformat())

    # Load chaos config from DynamoDB
    config = _load_config()
    if not config or not config.get("enabled", False):
        logger.info("chaos disabled, skipping")
        return {"statusCode": 200, "body": "chaos disabled"}

    severity_level = config.get("severity", "moderate")
    scenarios = config.get("scenarios", [])

    injected = []
    for scenario in scenarios:
        scenario_id = scenario["id"]
        scenario_severity = scenario.get("severity", "moderate")

        # Severity gating
        if SEVERITY_ORDER.get(scenario_severity, 0) > SEVERITY_ORDER.get(severity_level, 1):
            continue

        # Probability check
        probability = scenario.get("probability", 0.0)
        if random.random() > probability:
            continue

        # Cooldown check
        cooldown = scenario.get("cooldown_minutes", 20)
        if _is_in_cooldown(scenario_id, cooldown, now):
            logger.info("scenario %s in cooldown, skipping", scenario_id)
            continue

        # Select target pipeline
        target_pattern = scenario.get("target", "*")
        target = _select_target(target_pattern)
        if not target:
            continue

        # Execute scenario
        fn = SCENARIO_REGISTRY.get(scenario_id)
        if not fn:
            logger.warning("unknown scenario: %s", scenario_id)
            continue

        try:
            ctx = {
                "table_name": TABLE_NAME,
                "bucket_name": BUCKET_NAME,
                "state_machine_arn": STATE_MACHINE_ARN,
                "pipeline_id": target,
                "now": now,
                "scenario": scenario,
            }
            details = fn(ctx)
            _record_chaos_event(scenario_id, target, details, scenario, now)
            injected.append({"scenario": scenario_id, "target": target})
            logger.info("injected chaos: %s on %s", scenario_id, target)
        except Exception:
            logger.exception("failed to inject chaos scenario %s", scenario_id)

    # Run recovery checker
    recovered, unrecovered = check_recovery(TABLE_NAME, now)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "injected": injected,
            "recovered": recovered,
            "unrecovered": unrecovered,
        }),
    }


def _load_config():
    """Load chaos config from DynamoDB CHAOS#CONFIG record."""
    try:
        resp = ddb.get_item(
            TableName=TABLE_NAME,
            Key={"PK": {"S": "CHAOS#CONFIG"}, "SK": {"S": "CURRENT"}},
        )
        item = resp.get("Item")
        if not item:
            return None
        data = item.get("data", {}).get("S", "{}")
        return json.loads(data)
    except ClientError:
        logger.exception("failed to load chaos config")
        return None


def _is_in_cooldown(scenario_id, cooldown_minutes, now):
    """Check if the scenario was recently injected (within cooldown period)."""
    cutoff = now - timedelta(minutes=cooldown_minutes)
    try:
        resp = ddb.query(
            TableName=TABLE_NAME,
            KeyConditionExpression="PK = :pk AND SK > :cutoff",
            ExpressionAttributeValues={
                ":pk": {"S": "CHAOS#EVENTS"},
                ":cutoff": {"S": cutoff.isoformat()},
            },
            ScanIndexForward=False,
            Limit=50,
        )
        for item in resp.get("Items", []):
            if item.get("scenario", {}).get("S", "") == scenario_id:
                return True
    except ClientError:
        logger.exception("error checking cooldown for %s", scenario_id)
    return False


def _select_target(pattern):
    """Select a target pipeline based on pattern."""
    if pattern == "*":
        return random.choice(PIPELINES)
    candidates = [p for p in PIPELINES if _matches_pattern(p, pattern)]
    if not candidates:
        return None
    return random.choice(candidates)


def _matches_pattern(pipeline_id, pattern):
    """Simple pattern matching: '*' prefix/suffix matching."""
    if pattern == "*":
        return True
    if pattern.startswith("*"):
        return pipeline_id.endswith(pattern[1:])
    if pattern.endswith("*"):
        return pipeline_id.startswith(pattern[:-1])
    return pipeline_id == pattern


def _record_chaos_event(scenario_id, target, details, scenario_config, now):
    """Write a CHAOS# event record to DynamoDB."""
    ts = now.isoformat()
    ttl = int(now.timestamp()) + (30 * 86400)
    recovery_timeout = scenario_config.get("recovery_timeout_minutes", 60)

    item = {
        "PK": {"S": "CHAOS#EVENTS"},
        "SK": {"S": f"{ts}#{scenario_id}"},
        "GSI1PK": {"S": "CHAOS"},
        "GSI1SK": {"S": f"{ts}#{scenario_id}"},
        "scenario": {"S": scenario_id},
        "target": {"S": target},
        "category": {"S": scenario_config.get("category", "unknown")},
        "severity": {"S": scenario_config.get("severity", "unknown")},
        "status": {"S": "INJECTED"},
        "injectedAt": {"S": ts},
        "details": {"S": json.dumps(details or {})},
        "recoveryTimeoutMinutes": {"N": str(recovery_timeout)},
        "ttl": {"N": str(ttl)},
    }

    ddb.put_item(TableName=TABLE_NAME, Item=item)
