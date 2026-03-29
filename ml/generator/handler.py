"""ML feature generator Lambda.

Generates synthetic raw feature CSVs for a classification model pipeline.
Features: age, income, credit_score, employment_years, debt_ratio, num_accounts.

Uses a seeded PRNG for reproducibility when RANDOM_SEED is set.
"""

import csv
import io
import json
import logging
import os
import random
from datetime import datetime, timezone

import boto3
import botocore.exceptions

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")

_S3_BUCKET = os.environ["S3_BUCKET"]
_ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
_RANDOM_SEED = os.environ.get("RANDOM_SEED")
_ROW_COUNT = int(os.environ.get("ROW_COUNT", "1000"))

_FEATURE_COLUMNS = [
    "age",
    "income",
    "credit_score",
    "employment_years",
    "debt_ratio",
    "num_accounts",
    "label",
]


def _generate_row(rng: random.Random) -> dict:
    """Generate a single feature row with realistic distributions."""
    age = rng.randint(18, 80)
    income = round(rng.gauss(55000, 20000), 2)
    income = max(15000.0, income)  # Floor at minimum wage
    credit_score = rng.randint(300, 850)
    employment_years = rng.randint(0, min(age - 18, 45))
    debt_ratio = round(rng.uniform(0.0, 1.0), 4)
    num_accounts = rng.randint(1, 15)

    # Deterministic label based on features.
    score = (
        (credit_score - 300) / 550 * 0.4
        + min(income / 100000, 1.0) * 0.3
        + (1 - debt_ratio) * 0.2
        + min(employment_years / 20, 1.0) * 0.1
    )
    label = 1 if score >= 0.5 else 0

    return {
        "age": age,
        "income": income,
        "credit_score": credit_score,
        "employment_years": employment_years,
        "debt_ratio": debt_ratio,
        "num_accounts": num_accounts,
        "label": label,
    }


def _generate_csv(rng: random.Random, row_count: int) -> str:
    """Generate a CSV string with feature data."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FEATURE_COLUMNS)
    writer.writeheader()

    for _ in range(row_count):
        writer.writerow(_generate_row(rng))

    return output.getvalue()


def lambda_handler(event: dict, context: object) -> dict:
    """Generate synthetic feature CSV and write to S3."""
    rng = random.Random(_RANDOM_SEED) if _RANDOM_SEED else random.Random()

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")

    csv_data = _generate_csv(rng, _ROW_COUNT)

    s3_key = f"ml/raw/features_{date_str}.csv"

    try:
        _s3.put_object(
            Bucket=_S3_BUCKET,
            Key=s3_key,
            Body=csv_data.encode("utf-8"),
            ContentType="text/csv",
        )
    except botocore.exceptions.ClientError as exc:
        logger.error("ml-generator: S3 put_object failed -- %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }

    logger.info(
        "ml-generator: wrote %d rows to s3://%s/%s",
        _ROW_COUNT,
        _S3_BUCKET,
        s3_key,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "rows_generated": _ROW_COUNT,
            "s3_key": s3_key,
            "timestamp": now.isoformat(),
        }),
    }
