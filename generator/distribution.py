import math
from datetime import datetime, timedelta


def traffic_weight(hour: float) -> float:
    return (
        0.10
        + 0.70 * math.exp(-((hour - 10) ** 2) / 18)
        + 0.50 * math.exp(-((hour - 20) ** 2) / 12.5)
    )


def floor_to_window(dt: datetime) -> datetime:
    minute = dt.minute - (dt.minute % 15)
    return dt.replace(minute=minute, second=0, microsecond=0)


def compute_window_records(daily_target: int, window_start: datetime) -> int:
    midpoint_hour = window_start.hour + (window_start.minute + 7.5) / 60.0

    weight = traffic_weight(midpoint_hour)

    day_start = window_start.replace(hour=0, minute=0, second=0, microsecond=0)
    total_weight = 0.0
    for i in range(96):
        w = day_start + timedelta(minutes=15 * i)
        mid = w.hour + (w.minute + 7.5) / 60.0
        total_weight += traffic_weight(mid)

    return round(daily_target * weight / total_weight)
