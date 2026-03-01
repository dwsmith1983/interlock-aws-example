import hashlib
import math
import random
from datetime import datetime, timedelta, timezone

from generator.phones import pick_phone, pick_phone_pair
from generator.towers import (
    generate_mobile_path,
    get_tower_at_time,
    pick_tower,
)
from generator.websites import pick_website

WINDOW_MINUTES = 15
PING_INTERVAL_S = 10.0

# CDR parameters
CDR_MEAN_DURATION_S = 120.0
CDR_MIN_DURATION_S = 10.0
CDR_MAX_DURATION_S = 900.0
CDR_AVG_PINGS_PER_CALL = 12

# SEQ parameters
SEQ_LOGNORMAL_MU = math.log(20 * 60)  # median 20 min in seconds
SEQ_LOGNORMAL_SIGMA = 0.5
SEQ_MIN_DURATION_S = 600.0   # 10 min
SEQ_MAX_DURATION_S = 3600.0  # 60 min
SEQ_AVG_PINGS_PER_SESSION = 500

MOBILE_FRACTION = 0.10


def make_seed(stream: str, window_start: datetime) -> int:
    raw = f"{stream}:{window_start.isoformat()}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return int(digest[:16], 16)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _format_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_cdr_sessions(
    rng: random.Random,
    session_start_lo: datetime,
    session_start_hi: datetime,
    filter_lo: datetime,
    filter_hi: datetime,
    num_calls: int,
) -> list[dict]:
    records: list[dict] = []
    window_seconds = (session_start_hi - session_start_lo).total_seconds()

    for _ in range(num_calls):
        phone_out, phone_in = pick_phone_pair(rng)
        duration = _clamp(
            rng.expovariate(1.0 / CDR_MEAN_DURATION_S),
            CDR_MIN_DURATION_S,
            CDR_MAX_DURATION_S,
        )
        start_offset = rng.random() * window_seconds
        call_start = session_start_lo + timedelta(seconds=start_offset)

        is_mobile = rng.random() < MOBILE_FRACTION
        tower = pick_tower(rng)

        if is_mobile:
            path = generate_mobile_path(rng, tower, duration)
        else:
            path = None

        num_pings = max(1, int(duration / PING_INTERVAL_S))
        for i in range(num_pings):
            t = call_start + timedelta(seconds=i * PING_INTERVAL_S)
            if t < filter_lo or t >= filter_hi:
                continue

            if path is not None:
                cell_tower = get_tower_at_time(path, i * PING_INTERVAL_S)
            else:
                cell_tower = tower

            records.append({
                "phone_out": phone_out,
                "phone_in": phone_in,
                "cell_tower": cell_tower,
                "time": _format_time(t),
            })

    return records


def _generate_seq_sessions(
    rng: random.Random,
    session_start_lo: datetime,
    session_start_hi: datetime,
    filter_lo: datetime,
    filter_hi: datetime,
    num_sessions: int,
) -> list[dict]:
    records: list[dict] = []
    window_seconds = (session_start_hi - session_start_lo).total_seconds()

    for _ in range(num_sessions):
        phone = pick_phone(rng)
        duration = _clamp(
            rng.lognormvariate(SEQ_LOGNORMAL_MU, SEQ_LOGNORMAL_SIGMA),
            SEQ_MIN_DURATION_S,
            SEQ_MAX_DURATION_S,
        )
        start_offset = rng.random() * window_seconds
        session_start = session_start_lo + timedelta(seconds=start_offset)

        is_mobile = rng.random() < MOBILE_FRACTION
        tower = pick_tower(rng)
        if is_mobile:
            path = generate_mobile_path(rng, tower, duration)
        else:
            path = None

        # Determine site visits for this session
        num_visits = min(15, max(3, rng.randint(3, 15)))
        remaining_duration = duration
        elapsed = 0.0

        for v in range(num_visits):
            if remaining_duration <= 0:
                break

            host_name, site_name = pick_website(rng)

            # Pings per visit: 5-50, weighted toward more for streaming sites
            if site_name in ("YouTube", "Netflix", "Twitch", "Spotify",
                             "Disney+", "Hulu", "HBO Max"):
                pings_this_visit = rng.randint(20, 50)
            else:
                pings_this_visit = rng.randint(5, 30)

            visit_duration = pings_this_visit * PING_INTERVAL_S
            if visit_duration > remaining_duration:
                pings_this_visit = max(1, int(remaining_duration / PING_INTERVAL_S))
                visit_duration = pings_this_visit * PING_INTERVAL_S

            for i in range(pings_this_visit):
                t = session_start + timedelta(seconds=elapsed + i * PING_INTERVAL_S)
                if t < filter_lo or t >= filter_hi:
                    continue

                if path is not None:
                    cell_tower = get_tower_at_time(
                        path, elapsed + i * PING_INTERVAL_S
                    )
                else:
                    cell_tower = tower

                records.append({
                    "phone_number": phone,
                    "cell_tower": cell_tower,
                    "host_name": host_name,
                    "site_name": site_name,
                    "time": _format_time(t),
                })

            elapsed += visit_duration
            remaining_duration -= visit_duration

    return records


def generate_window(
    stream: str, window_start: datetime, daily_target: int
) -> list[dict]:
    from generator.distribution import compute_window_records

    target_records = compute_window_records(daily_target, window_start)
    window_end = window_start + timedelta(minutes=WINDOW_MINUTES)
    prev_window_start = window_start - timedelta(minutes=WINDOW_MINUTES)

    # Current window sessions
    current_seed = make_seed(stream, window_start)
    current_rng = random.Random(current_seed)

    # Previous window sessions (for spillover)
    prev_seed = make_seed(stream, prev_window_start)
    prev_rng = random.Random(prev_seed)

    if stream == "cdr":
        num_calls = max(1, target_records // CDR_AVG_PINGS_PER_CALL)
        prev_calls = max(1, compute_window_records(daily_target, prev_window_start) // CDR_AVG_PINGS_PER_CALL)

        current_records = _generate_cdr_sessions(
            current_rng, window_start, window_end,
            filter_lo=window_start, filter_hi=window_end,
            num_calls=num_calls,
        )
        spillover_records = _generate_cdr_sessions(
            prev_rng, prev_window_start, window_start,
            filter_lo=window_start, filter_hi=window_end,
            num_calls=prev_calls,
        )
    elif stream == "seq":
        num_sessions = max(1, target_records // SEQ_AVG_PINGS_PER_SESSION)
        prev_sessions = max(1, compute_window_records(daily_target, prev_window_start) // SEQ_AVG_PINGS_PER_SESSION)

        current_records = _generate_seq_sessions(
            current_rng, window_start, window_end,
            filter_lo=window_start, filter_hi=window_end,
            num_sessions=num_sessions,
        )
        spillover_records = _generate_seq_sessions(
            prev_rng, prev_window_start, window_start,
            filter_lo=window_start, filter_hi=window_end,
            num_sessions=prev_sessions,
        )
    else:
        raise ValueError(f"Unknown stream: {stream}")

    all_records = current_records + spillover_records
    all_records.sort(key=lambda r: r["time"])
    return all_records
