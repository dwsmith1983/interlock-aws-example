"""Banking transaction generator Lambda.

Produces simulated banking transactions to a Kinesis stream at variable
rates.  Normal intraday volume with a COB (close-of-business) spike.

Uses a seeded PRNG for reproducibility when RANDOM_SEED is set.
"""

import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_kinesis = boto3.client("kinesis")

_STREAM_NAME = os.environ["KINESIS_STREAM_NAME"]
_BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "100"))
_COB_HOUR = int(os.environ.get("COB_HOUR", "17"))
_RANDOM_SEED = os.environ.get("RANDOM_SEED")

_TRANSACTION_TYPES = ("deposit", "withdrawal", "transfer", "payment", "refund")
_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "SGD")
_REGIONS = ("US", "EU", "APAC")

# Kinesis PutRecords accepts max 500 records per call.
_MAX_KINESIS_BATCH = 500


def _build_transaction(rng: random.Random, now_iso: str) -> dict:
    """Generate a single simulated banking transaction."""
    return {
        "transaction_id": str(uuid.uuid4()),
        "account_id": f"ACCT-{rng.randint(100000, 999999)}",
        "type": rng.choice(_TRANSACTION_TYPES),
        "amount": round(rng.uniform(1.0, 50000.0), 2),
        "currency": rng.choice(_CURRENCIES),
        "timestamp": now_iso,
        "region": rng.choice(_REGIONS),
    }


def _send_records(records: list[dict]) -> int:
    """Send records to Kinesis in batches, return total successfully sent."""
    sent = 0
    for i in range(0, len(records), _MAX_KINESIS_BATCH):
        batch = records[i : i + _MAX_KINESIS_BATCH]
        response = _kinesis.put_records(
            StreamName=_STREAM_NAME,
            Records=batch,
        )
        sent += len(batch) - response.get("FailedRecordCount", 0)
    return sent


def lambda_handler(event: dict, context: object) -> dict:
    """Generate and send a batch of transactions to Kinesis."""
    rng = random.Random(_RANDOM_SEED) if _RANDOM_SEED else random.Random()

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    is_cob = now.hour == _COB_HOUR

    # COB spike: 5x normal volume.
    count = _BATCH_SIZE * 5 if is_cob else _BATCH_SIZE

    records = [
        {
            "Data": json.dumps(_build_transaction(rng, now_iso)).encode("utf-8"),
            "PartitionKey": f"ACCT-{rng.randint(100000, 999999)}",
        }
        for _ in range(count)
    ]

    sent = _send_records(records)

    logger.info(
        "banking-generator: sent %d/%d transactions (cob=%s)",
        sent,
        count,
        is_cob,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "transactions_sent": sent,
            "is_cob": is_cob,
            "timestamp": now_iso,
        }),
    }
