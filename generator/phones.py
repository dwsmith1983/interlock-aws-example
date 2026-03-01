import random

_POOL_SIZE = 500_000
_SEED = 42

_phones: list[str] | None = None


def _generate_pool() -> list[str]:
    rng = random.Random(_SEED)
    phones: set[str] = set()
    while len(phones) < _POOL_SIZE:
        area = rng.randint(200, 999)
        exchange = rng.randint(200, 999)
        subscriber = rng.randint(0, 9999)
        phones.add(f"{area}{exchange}{subscriber:04d}")
    return sorted(phones)


def get_phones() -> list[str]:
    global _phones
    if _phones is None:
        _phones = _generate_pool()
    return _phones


def pick_phone(rng: random.Random) -> str:
    pool = get_phones()
    return pool[rng.randint(0, len(pool) - 1)]


def pick_phone_pair(rng: random.Random) -> tuple[str, str]:
    pool = get_phones()
    a = rng.randint(0, len(pool) - 1)
    b = rng.randint(0, len(pool) - 2)
    if b >= a:
        b += 1
    return pool[a], pool[b]
