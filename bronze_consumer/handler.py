import base64
import json
import logging

from bronze_consumer.delta_writer import write_bronze_cdr, write_bronze_seq
from bronze_consumer.hasher import PhoneHasher
from bronze_consumer.s3_reader import read_jsonl_gz

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_hasher = PhoneHasher()


def lambda_handler(event: dict, context) -> dict:
    """Process a batch of Kinesis records, each containing an S3 PutObject event."""
    processed = 0
    errors = 0

    for record in event.get("Records", []):
        try:
            payload = base64.b64decode(record["kinesis"]["data"])
            s3_event = json.loads(payload)

            bucket = s3_event["detail"]["bucket"]["name"]
            key = s3_event["detail"]["object"]["key"]

            # Determine stream type from S3 key prefix
            if key.startswith("cdr/"):
                stream = "cdr"
            elif key.startswith("seq/"):
                stream = "seq"
            else:
                logger.warning("Skipping unknown prefix: %s", key)
                continue

            # Skip non-data files
            if not key.endswith(".jsonl.gz"):
                logger.info("Skipping non-JSONL file: %s", key)
                continue

            logger.info("Processing %s: s3://%s/%s", stream, bucket, key)
            records = read_jsonl_gz(bucket, key)

            if not records:
                logger.info("No records in %s", key)
                continue

            # Collect all phone numbers for hashing
            if stream == "cdr":
                phones = set()
                for rec in records:
                    phones.add(rec["phone_out"])
                    phones.add(rec["phone_in"])
                phone_hashes = _hasher.hash_phones(list(phones))
                written = write_bronze_cdr(records, phone_hashes, bucket)
            else:
                phones = {rec["phone_number"] for rec in records}
                phone_hashes = _hasher.hash_phones(list(phones))
                written = write_bronze_seq(records, phone_hashes, bucket)

            logger.info("Wrote %d bronze records for %s", written, key)
            processed += 1

        except Exception:
            logger.exception("Error processing record")
            errors += 1

    result = {"processed": processed, "errors": errors}
    logger.info("Batch complete: %s", result)

    if errors > 0:
        raise RuntimeError(f"Failed to process {errors} record(s)")

    return result
