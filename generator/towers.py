from __future__ import annotations

import bisect
import json
import math
import os
import random
from collections import defaultdict

_REF_DIR = os.path.join(os.path.dirname(__file__), "reference")

with open(os.path.join(_REF_DIR, "towers.json")) as _f:
    TOWERS: list[dict] = json.load(_f)

_TOWER_IDS: list[str] = [t["tower_id"] for t in TOWERS]

_CITY_INDEX: dict[str, list[str]] = defaultdict(list)
for _t in TOWERS:
    _CITY_INDEX[_t["city"]].append(_t["tower_id"])

_TOWER_LOOKUP: dict[str, dict] = {t["tower_id"]: t for t in TOWERS}

_EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_adjacency() -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for tower in TOWERS:
        tid = tower["tower_id"]
        lat1, lon1 = tower["lat"], tower["lon"]
        dists: list[tuple[float, str]] = []
        for other in TOWERS:
            oid = other["tower_id"]
            if oid == tid:
                continue
            d = haversine(lat1, lon1, other["lat"], other["lon"])
            dists.append((d, oid))
        dists.sort()
        neighbors: list[str] = [oid for _, oid in dists[:3]]
        for d, oid in dists[3:5]:
            if d <= 10.0:
                neighbors.append(oid)
            else:
                break
        adj[tid] = neighbors
    return adj


ADJACENCY: dict[str, list[str]] = _build_adjacency()


def pick_tower(rng: random.Random) -> str:
    return rng.choice(_TOWER_IDS)


def pick_tower_in_city(rng: random.Random, city: str) -> str:
    return rng.choice(_CITY_INDEX[city])


def generate_mobile_path(
    rng: random.Random, start_tower: str, duration_s: float
) -> list[tuple[float, str]]:
    path: list[tuple[float, str]] = [(0.0, start_tower)]
    t = 0.0
    current = start_tower
    while t < duration_s:
        step = rng.uniform(30.0, 60.0)
        t += step
        if t >= duration_s:
            break
        neighbors = ADJACENCY.get(current, [])
        if not neighbors:
            break
        current = rng.choice(neighbors)
        path.append((t, current))
    return path


def get_tower_at_time(path: list[tuple[float, str]], time_offset: float) -> str:
    times = [entry[0] for entry in path]
    idx = bisect.bisect_right(times, time_offset) - 1
    if idx < 0:
        idx = 0
    return path[idx][1]
