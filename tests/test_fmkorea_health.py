from datetime import datetime

import check_fmkorea_health as health

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


def test_healthy_response_automatically_resolves_open_alert(monkeypatch, tmp_path):
    now = datetime.now()
    log_line = (
        f"{now:%Y-%m-%d %H:%M:%S},000 [INFO] "
        "[FM디버그] status=200 len=72531 tr=24 cate=23 normal=20"
    )
    resolved = []
    saved_states = []

    monkeypatch.setattr(health, "tail_lines", lambda _: [log_line])
    monkeypatch.setattr(
        health,
        "resolve_alert",
        lambda alert_key, note: resolved.append((alert_key, note)) or True,
    )
    monkeypatch.setattr(
        health,
        "save_state",
        lambda _, state: saved_states.append(state.copy()),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_fmkorea_health.py",
            "--log-path",
            str(tmp_path / "fmkorea.log"),
            "--state-path",
            str(tmp_path / "health-state.json"),
            "--no-notify",
        ],
    )

    assert health.main() == 0
    assert resolved == [
        (
            health.DEFAULT_ALERT_KEY,
            "FM코리아 정상 응답 확인으로 자동 처리 완료",
        )
    ]
    assert saved_states[-1]["last_status"] == 200
