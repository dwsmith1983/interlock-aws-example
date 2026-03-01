#!/usr/bin/env python3
"""Generate tower reference data for 50 US metro areas (2000 towers total).

Each metro gets 40 towers scattered randomly within ~10-15 km of its center.
tower_id is the first 8 hex chars of md5("{lat},{lon}").

Output: generator/reference/towers.json
"""

import hashlib
import json
import math
import os
import random

SEED = 42
TOWERS_PER_METRO = 40
# ~10-15 km radius expressed in degrees (rough mid-latitude approximation)
SCATTER_KM_MIN = 2.0
SCATTER_KM_MAX = 15.0
KM_PER_DEG_LAT = 111.0  # ~111 km per degree of latitude

METROS = [
    ("New York", "NY", 40.7128, -74.0060),
    ("Los Angeles", "CA", 34.0522, -118.2437),
    ("Chicago", "IL", 41.8781, -87.6298),
    ("Houston", "TX", 29.7604, -95.3698),
    ("Phoenix", "AZ", 33.4484, -112.0740),
    ("Philadelphia", "PA", 39.9526, -75.1652),
    ("San Antonio", "TX", 29.4241, -98.4936),
    ("San Diego", "CA", 32.7157, -117.1611),
    ("Dallas", "TX", 32.7767, -96.7970),
    ("San Jose", "CA", 37.3382, -121.8863),
    ("Austin", "TX", 30.2672, -97.7431),
    ("Jacksonville", "FL", 30.3322, -81.6557),
    ("Fort Worth", "TX", 32.7555, -97.3308),
    ("Columbus", "OH", 39.9612, -82.9988),
    ("Charlotte", "NC", 35.2271, -80.8431),
    ("Indianapolis", "IN", 39.7684, -86.1581),
    ("San Francisco", "CA", 37.7749, -122.4194),
    ("Seattle", "WA", 47.6062, -122.3321),
    ("Denver", "CO", 39.7392, -104.9903),
    ("Washington", "DC", 38.9072, -77.0369),
    ("Nashville", "TN", 36.1627, -86.7816),
    ("Oklahoma City", "OK", 35.4676, -97.5164),
    ("El Paso", "TX", 31.7619, -106.4850),
    ("Boston", "MA", 42.3601, -71.0589),
    ("Portland", "OR", 45.5152, -122.6784),
    ("Las Vegas", "NV", 36.1699, -115.1398),
    ("Memphis", "TN", 35.1495, -90.0490),
    ("Louisville", "KY", 38.2527, -85.7585),
    ("Baltimore", "MD", 39.2904, -76.6122),
    ("Milwaukee", "WI", 43.0389, -87.9065),
    ("Albuquerque", "NM", 35.0844, -106.6504),
    ("Tucson", "AZ", 32.2226, -110.9747),
    ("Fresno", "CA", 36.7378, -119.7871),
    ("Sacramento", "CA", 38.5816, -121.4944),
    ("Mesa", "AZ", 33.4152, -111.8315),
    ("Kansas City", "MO", 39.0997, -94.5786),
    ("Atlanta", "GA", 33.7490, -84.3880),
    ("Omaha", "NE", 41.2565, -95.9345),
    ("Colorado Springs", "CO", 38.8339, -104.8214),
    ("Raleigh", "NC", 35.7796, -78.6382),
    ("Long Beach", "CA", 33.7701, -118.1937),
    ("Virginia Beach", "VA", 36.8529, -75.9780),
    ("Miami", "FL", 25.7617, -80.1918),
    ("Oakland", "CA", 37.8044, -122.2712),
    ("Minneapolis", "MN", 44.9778, -93.2650),
    ("Tampa", "FL", 27.9506, -82.4572),
    ("Tulsa", "OK", 36.1540, -95.9928),
    ("Arlington", "TX", 32.7357, -97.1081),
    ("New Orleans", "LA", 29.9511, -90.0715),
    ("Detroit", "MI", 42.3314, -83.0458),
]


def make_tower_id(lat: float, lon: float) -> str:
    raw = f"{lat},{lon}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def scatter_point(
    rng: random.Random, center_lat: float, center_lon: float
) -> tuple[float, float]:
    """Return a point scattered randomly ~2-15 km from the center."""
    dist_km = rng.uniform(SCATTER_KM_MIN, SCATTER_KM_MAX)
    bearing = rng.uniform(0, 2 * math.pi)

    dlat = (dist_km * math.cos(bearing)) / KM_PER_DEG_LAT
    # Adjust longitude degrees by latitude to keep distances realistic
    km_per_deg_lon = KM_PER_DEG_LAT * math.cos(math.radians(center_lat))
    dlon = (dist_km * math.sin(bearing)) / km_per_deg_lon

    return round(center_lat + dlat, 4), round(center_lon + dlon, 4)


def main() -> None:
    rng = random.Random(SEED)
    towers: list[dict] = []

    for city, state, clat, clon in METROS:
        for _ in range(TOWERS_PER_METRO):
            lat, lon = scatter_point(rng, clat, clon)
            towers.append(
                {
                    "tower_id": make_tower_id(lat, lon),
                    "lat": lat,
                    "lon": lon,
                    "city": city,
                    "state": state,
                }
            )

    # Verify uniqueness of tower_ids
    ids = [t["tower_id"] for t in towers]
    assert len(ids) == len(set(ids)), "Duplicate tower_id detected"

    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "generator",
        "reference",
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "towers.json")

    with open(out_path, "w") as f:
        json.dump(towers, f, indent=2)
        f.write("\n")

    print(f"Wrote {len(towers)} towers to {out_path}")


if __name__ == "__main__":
    main()
