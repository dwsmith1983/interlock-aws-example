"""Category 1: Infrastructure Chaos — killing running things.

Scenarios:
- sfn-kill: Stop a running Step Function execution
- lambda-throttle: Throttle a Go Lambda to 0 concurrency
- lambda-throttle-ingest: Throttle an ingestion Lambda to 0 concurrency
"""

import logging
import time
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger(__name__)

sfn_client = boto3.client("stepfunctions")
lambda_client = boto3.client("lambda")

GO_LAMBDA_SUFFIXES = ["evaluator", "orchestrator", "trigger", "run-checker"]
INGEST_LAMBDA_SUFFIXES = ["ingest-earthquake", "ingest-crypto"]


def sfn_kill(ctx):
    """Kill a random running Step Function execution."""
    state_machine_arn = ctx["state_machine_arn"]
    if not state_machine_arn:
        logger.warning("no state_machine_arn configured, skipping sfn-kill")
        return {"skipped": True, "reason": "no state_machine_arn"}

    resp = sfn_client.list_executions(
        stateMachineArn=state_machine_arn,
        statusFilter="RUNNING",
        maxResults=10,
    )
    executions = resp.get("executions", [])
    if not executions:
        logger.info("no running executions to kill")
        return {"skipped": True, "reason": "no running executions"}

    import random
    target_exec = random.choice(executions)
    exec_arn = target_exec["executionArn"]

    sfn_client.stop_execution(
        executionArn=exec_arn,
        cause="chaos-test: sfn-kill scenario",
    )
    logger.info("killed SFN execution %s", exec_arn)
    return {"executionArn": exec_arn, "action": "stopped"}


def lambda_throttle(ctx):
    """Throttle a random Go Lambda (evaluator/trigger/orchestrator/run-checker) to 0 concurrency."""
    scenario = ctx["scenario"]
    duration_minutes = scenario.get("throttle_duration_minutes", 5)

    target_fn = _find_lambda(GO_LAMBDA_SUFFIXES)
    if not target_fn:
        return {"skipped": True, "reason": "no matching Go Lambda found"}

    lambda_client.put_function_concurrency(
        FunctionName=target_fn,
        ReservedConcurrentExecutions=0,
    )
    logger.info("throttled Lambda %s to 0 concurrency for %d minutes", target_fn, duration_minutes)

    # Schedule restore (best-effort via sleep in a thread — chaos controller restores on next cycle)
    return {
        "functionName": target_fn,
        "action": "throttled",
        "durationMinutes": duration_minutes,
        "restoreBy": (ctx["now"] + timedelta(minutes=duration_minutes)).isoformat(),
    }


def lambda_throttle_ingest(ctx):
    """Throttle an ingestion Lambda to 0 concurrency."""
    scenario = ctx["scenario"]
    duration_minutes = scenario.get("throttle_duration_minutes", 10)

    target_fn = _find_lambda(INGEST_LAMBDA_SUFFIXES)
    if not target_fn:
        return {"skipped": True, "reason": "no matching ingest Lambda found"}

    lambda_client.put_function_concurrency(
        FunctionName=target_fn,
        ReservedConcurrentExecutions=0,
    )
    logger.info("throttled ingest Lambda %s to 0 concurrency for %d minutes", target_fn, duration_minutes)

    return {
        "functionName": target_fn,
        "action": "throttled",
        "durationMinutes": duration_minutes,
        "restoreBy": (ctx["now"] + timedelta(minutes=duration_minutes)).isoformat(),
    }


def _find_lambda(suffixes):
    """Find a Lambda function matching one of the given suffixes."""
    import random
    try:
        resp = lambda_client.list_functions(MaxItems=50)
        functions = resp.get("Functions", [])
        candidates = []
        for fn in functions:
            name = fn["FunctionName"]
            for suffix in suffixes:
                if suffix in name:
                    candidates.append(name)
                    break
        if candidates:
            return random.choice(candidates)
    except Exception:
        logger.exception("error listing Lambda functions")
    return None
