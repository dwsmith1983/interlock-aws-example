"""Tests for generator session spillover capture."""
import math
from datetime import datetime, timezone

from generator.sessions import generate_window, WINDOW_MINUTES


def _traffic_weight(hour: float) -> float:
    return (
        0.10
        + 0.70 * math.exp(-((hour - 10) ** 2) / 18)
        + 0.50 * math.exp(-((hour - 20) ** 2) / 12.5)
    )


def test_seq_no_duplicate_pings():
    """Every SEQ ping should appear in exactly one window's output."""
    from datetime import timedelta

    daily_target = 1_000_000
    all_records: dict[tuple[str, str], int] = {}
    base = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
    for i in range(8):
        ws = base + timedelta(minutes=i * WINDOW_MINUTES)
        records = generate_window("seq", ws, daily_target)
        for r in records:
            key = (r["phone_number"], r["time"])
            all_records[key] = all_records.get(key, 0) + 1

    dupes = {k: v for k, v in all_records.items() if v > 1}
    assert len(dupes) == 0, f"Found {len(dupes)} duplicate pings"


def test_seq_spillover_captures_long_sessions():
    """Sessions >15 min should have pings captured across multiple windows."""
    daily_target = 1_000_000
    ws = datetime(2026, 3, 4, 10, 15, tzinfo=timezone.utc)
    records = generate_window("seq", ws, daily_target)
    assert len(records) > 0
    for r in records:
        t = r["time"]
        assert "T10:1" in t or "T10:2" in t, f"Record time {t} outside [10:15, 10:30)"


def test_cdr_generates_records():
    """CDR generation should work for basic case."""
    daily_target = 1_000_000
    ws = datetime(2026, 3, 4, 10, 15, tzinfo=timezone.utc)
    records = generate_window("cdr", ws, daily_target)
    assert len(records) > 0


def test_seq_pct_of_expected_above_threshold():
    """After spillover fix, actual/expected should be >= 0.85 for all hours."""
    daily_target = 5_000_000

    failing = {}
    for hour in range(24):
        total_records = 0
        for m in [0, 15, 30, 45]:
            ws = datetime(2026, 3, 4, hour, m, tzinfo=timezone.utc)
            records = generate_window("seq", ws, daily_target)
            for r in records:
                if int(r["time"][11:13]) == hour:
                    total_records += 1

        total_weight = sum(
            _traffic_weight(i * 0.25 + 7.5 / 60.0) for i in range(96)
        )
        hour_weight = sum(
            _traffic_weight(hour + (m + 7.5) / 60.0) for m in [0, 15, 30, 45]
        )
        expected = round(daily_target * hour_weight / total_weight)
        pct = total_records / expected if expected > 0 else 0
        if pct < 0.85:
            failing[hour] = pct

    assert len(failing) == 0, (
        f"{len(failing)}/24 hours below 0.85: "
        + ", ".join(f"h{h}={v:.4f}" for h, v in sorted(failing.items()))
    )


def test_partition_by_timestamp_hour(monkeypatch):
    """Records with different timestamp hours go to different S3 keys."""
    from generator.generate import generate_and_upload

    uploaded = {}

    def mock_upload(bucket, key, data):
        uploaded[key] = data

    monkeypatch.setattr("generator.generate.upload_to_s3", mock_upload)

    ws = datetime(2026, 3, 4, 10, 45, tzinfo=timezone.utc)
    result = generate_and_upload("seq", ws, 10_000_000, "test-bucket")

    for key in uploaded:
        par_hour = key.split("par_hour=")[1].split("/")[0]
        assert len(par_hour) == 2
        assert 0 <= int(par_hour) <= 23
    assert result["total_records"] > 0
