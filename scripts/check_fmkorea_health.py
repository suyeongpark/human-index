"""
FM코리아 크롤러 상태 확인 및 macOS 알림.

최근 로그에서 FM코리아 응답이 연속 430이면 쿠키 갱신/차단 가능성을
macOS 알림으로 알려준다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_LOG_PATH = LOG_DIR / "fmkorea_launchd_err.log"
DEFAULT_STATE_PATH = LOG_DIR / "fmkorea_health_state.json"

STATUS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .*"
    r"\[FM디버그\] status=(?P<status>\d+)"
)


@dataclass(frozen=True)
class StatusEntry:
    timestamp: datetime
    status: int


def parse_status_entries(lines: list[str]) -> list[StatusEntry]:
    entries: list[StatusEntry] = []
    for line in lines:
        match = STATUS_RE.search(line)
        if not match:
            continue
        entries.append(
            StatusEntry(
                timestamp=datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S"),
                status=int(match.group("status")),
            )
        )
    return entries


def tail_lines(path: Path, max_bytes: int = 256_000) -> list[str]:
    if not path.exists():
        return []

    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        return f.read().decode("utf-8", errors="replace").splitlines()


def recent_entries(
    entries: list[StatusEntry],
    now: datetime,
    lookback_minutes: int,
) -> list[StatusEntry]:
    cutoff = now - timedelta(minutes=lookback_minutes)
    return [entry for entry in entries if entry.timestamp >= cutoff]


def has_consecutive_430(entries: list[StatusEntry], threshold: int) -> bool:
    if len(entries) < threshold:
        return False
    return all(entry.status == 430 for entry in entries[-threshold:])


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def should_notify(state: dict, now: datetime, cooldown_minutes: int) -> bool:
    last_alert = state.get("last_alert_at")
    if not last_alert:
        return True
    try:
        last_alert_at = datetime.fromisoformat(last_alert)
    except ValueError:
        return True
    return now - last_alert_at >= timedelta(minutes=cooldown_minutes)


def send_macos_notification(title: str, message: str) -> None:
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{safe_message}" with title "{safe_title}"',
        ],
        check=False,
    )


def build_alert_message(entries: list[StatusEntry]) -> str:
    latest = entries[-1]
    return (
        "FM코리아 크롤러가 연속 430 응답을 받았습니다. "
        f"쿠키 갱신 필요 가능성이 큽니다. 마지막 감지: {latest.timestamp:%H:%M:%S}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="FM코리아 크롤러 상태 확인")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--lookback-minutes", type=int, default=60)
    parser.add_argument("--consecutive-430", type=int, default=4)
    parser.add_argument("--cooldown-minutes", type=int, default=180)
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()

    now = datetime.now()
    state = load_state(args.state_path)
    entries = recent_entries(
        parse_status_entries(tail_lines(args.log_path)),
        now=now,
        lookback_minutes=args.lookback_minutes,
    )

    if not entries:
        state["last_check_at"] = now.isoformat()
        state["last_status"] = "missing"
        save_state(args.state_path, state)
        print("FM코리아 상태: 최근 로그 없음")
        return 0

    latest = entries[-1]
    state["last_check_at"] = now.isoformat()
    state["last_seen_at"] = latest.timestamp.isoformat()
    state["last_status"] = latest.status

    if has_consecutive_430(entries, args.consecutive_430):
        message = build_alert_message(entries)
        if should_notify(state, now, args.cooldown_minutes):
            if not args.no_notify:
                send_macos_notification("Human Index", message)
            state["last_alert_at"] = now.isoformat()
            print(f"FM코리아 경고: {message}")
        else:
            print("FM코리아 경고: 430 연속 감지, 쿨다운으로 알림 생략")
        save_state(args.state_path, state)
        return 0

    if latest.status == 200:
        state["last_healthy_at"] = latest.timestamp.isoformat()
    save_state(args.state_path, state)
    print(f"FM코리아 상태 정상: 최신 status={latest.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
