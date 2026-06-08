from datetime import datetime

from check_fmkorea_health import (
    has_consecutive_430,
    parse_status_entries,
    recent_entries,
)


def test_parse_status_entries_extracts_fmkorea_statuses():
    lines = [
        "2026-06-09 06:46:32,218 [INFO]   [FM디버그] status=200 len=72531 tr=24 cate=23 normal=20",
        "not a status line",
        "2026-06-09 06:47:58,192 [INFO]   [FM디버그] status=430 len=3865 tr=0 cate=0 normal=0",
    ]

    entries = parse_status_entries(lines)

    assert [entry.status for entry in entries] == [200, 430]
    assert entries[0].timestamp == datetime(2026, 6, 9, 6, 46, 32)


def test_has_consecutive_430_only_checks_latest_statuses():
    entries = parse_status_entries([
        "2026-06-09 06:46:32,218 [INFO]   [FM디버그] status=200 len=72531 tr=24 cate=23 normal=20",
        "2026-06-09 06:47:32,218 [INFO]   [FM디버그] status=430 len=3865 tr=0 cate=0 normal=0",
        "2026-06-09 06:48:32,218 [INFO]   [FM디버그] status=430 len=3865 tr=0 cate=0 normal=0",
        "2026-06-09 06:49:32,218 [INFO]   [FM디버그] status=430 len=3865 tr=0 cate=0 normal=0",
        "2026-06-09 06:50:32,218 [INFO]   [FM디버그] status=430 len=3865 tr=0 cate=0 normal=0",
    ])

    assert has_consecutive_430(entries, threshold=4)
    assert not has_consecutive_430(entries, threshold=5)


def test_recent_entries_filters_by_lookback_minutes():
    entries = parse_status_entries([
        "2026-06-09 05:46:32,218 [INFO]   [FM디버그] status=430 len=3865 tr=0 cate=0 normal=0",
        "2026-06-09 06:46:32,218 [INFO]   [FM디버그] status=200 len=72531 tr=24 cate=23 normal=20",
    ])

    recent = recent_entries(
        entries,
        now=datetime(2026, 6, 9, 6, 50, 0),
        lookback_minutes=30,
    )

    assert [entry.status for entry in recent] == [200]
