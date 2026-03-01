import hashlib
import os
from datetime import datetime, timezone

import boto3

_dynamodb = boto3.resource("dynamodb")
_TABLE_NAME = os.environ.get("PHONE_HASH_TABLE", "dev-phone-hash")
_SALT = os.environ.get("PHONE_HASH_SALT", "")

# Warm-invocation cache: persists across Lambda invocations in the same container
_cache: dict[str, str] = {}


def _compute_hash(phone: str) -> str:
    return hashlib.sha256((_SALT + phone).encode()).hexdigest()


class PhoneHasher:
    """Maps phone numbers to SHA-256 hashes, backed by DynamoDB for persistence."""

    def __init__(self) -> None:
        self._table = _dynamodb.Table(_TABLE_NAME)

    def hash_phones(self, phones: list[str]) -> dict[str, str]:
        """Return {phone: hash} for all given phone numbers.

        Uses in-memory cache first, then DynamoDB BatchGetItem for misses,
        then computes and writes new hashes via BatchWriteItem.
        """
        result: dict[str, str] = {}
        uncached: list[str] = []

        for phone in phones:
            if phone in _cache:
                result[phone] = _cache[phone]
            else:
                uncached.append(phone)

        if not uncached:
            return result

        # Deduplicate before querying DynamoDB
        uncached = list(set(uncached))

        # BatchGetItem — up to 100 keys per call
        still_missing: list[str] = []
        for i in range(0, len(uncached), 100):
            batch = uncached[i : i + 100]
            resp = _dynamodb.meta.client.batch_get_item(
                RequestItems={
                    _TABLE_NAME: {
                        "Keys": [{"phone": {"S": p}} for p in batch],
                        "ProjectionExpression": "phone, #h",
                        "ExpressionAttributeNames": {"#h": "hash"},
                    }
                }
            )
            for item in resp.get("Responses", {}).get(_TABLE_NAME, []):
                phone = item["phone"]["S"]
                h = item["hash"]["S"]
                _cache[phone] = h
                result[phone] = h

            found = {item["phone"]["S"] for item in resp.get("Responses", {}).get(_TABLE_NAME, [])}
            still_missing.extend(p for p in batch if p not in found)

        if not still_missing:
            return result

        # Compute hashes for missing phones and write to DynamoDB
        now = datetime.now(timezone.utc).isoformat()
        new_items: list[dict] = []
        for phone in still_missing:
            h = _compute_hash(phone)
            _cache[phone] = h
            result[phone] = h
            new_items.append({
                "PutRequest": {
                    "Item": {
                        "phone": {"S": phone},
                        "hash": {"S": h},
                        "created_at": {"S": now},
                    }
                }
            })

        # BatchWriteItem — up to 25 items per call
        for i in range(0, len(new_items), 25):
            batch = new_items[i : i + 25]
            _dynamodb.meta.client.batch_write_item(
                RequestItems={_TABLE_NAME: batch}
            )

        return result
