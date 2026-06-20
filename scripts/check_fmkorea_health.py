"""
FM코리아 크롤러 상태 확인 및 macOS 알림.

최근 로그에서 FM코리아 응답이 연속 430이면 쿠키 갱신/차단 가능성을
DB 알림 테이블에 열어두고, 처리 완료 전까지 macOS 알림으로 알려준다.
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

import psycopg2
from psycopg2.extras import Json

from db_config import DB_CONFIG


ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_LOG_PATH = LOG_DIR / "fmkorea_launchd_err.log"
DEFAULT_STATE_PATH = LOG_DIR / "fmkorea_health_state.json"
DEFAULT_ALERT_KEY = "fmkorea_cookie_430"

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


def connect_db():
    return psycopg2.connect(**DB_CONFIG)


def ensure_alert_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crawler_health_alerts (
            id BIGSERIAL PRIMARY KEY,
            alert_key VARCHAR(100) NOT NULL UNIQUE,
            source VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            severity VARCHAR(20) NOT NULL DEFAULT 'warning',
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            first_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_notified_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            resolution_note TEXT,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_crawler_health_alerts_status
                CHECK (status IN ('open', 'resolved'))
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_crawler_health_alerts_status
            ON crawler_health_alerts (status, source)
        """
    )


def resolve_alert(alert_key: str, note: str) -> bool:
    with connect_db() as conn:
        with conn.cursor() as cur:
            ensure_alert_table(cur)
            cur.execute(
                """
                UPDATE crawler_health_alerts
                SET status = 'resolved',
                    resolved_at = NOW(),
                    resolution_note = %s,
                    updated_at = NOW()
                WHERE alert_key = %s
                  AND status = 'open'
                """,
                (note, alert_key),
            )
            return cur.rowcount > 0


def open_or_update_alert(
    alert_key: str,
    source: str,
    title: str,
    message: str,
    details: dict,
) -> None:
    with connect_db() as conn:
        with conn.cursor() as cur:
            ensure_alert_table(cur)
            cur.execute(
                """
                INSERT INTO crawler_health_alerts
                    (alert_key, source, status, severity, title, message,
                     first_detected_at, last_detected_at, details, updated_at)
                VALUES
                    (%s, %s, 'open', 'warning', %s, %s, NOW(), NOW(), %s, NOW())
                ON CONFLICT (alert_key) DO UPDATE
                SET status = 'open',
                    severity = EXCLUDED.severity,
                    title = EXCLUDED.title,
                    message = EXCLUDED.message,
                    first_detected_at = CASE
                        WHEN crawler_health_alerts.status = 'resolved'
                        THEN NOW()
                        ELSE crawler_health_alerts.first_detected_at
                    END,
                    last_detected_at = NOW(),
                    resolved_at = NULL,
                    resolution_note = NULL,
                    details = EXCLUDED.details,
                    updated_at = NOW()
                """,
                (alert_key, source, title, message, Json(details)),
            )


def has_open_alert(alert_key: str) -> bool:
    with connect_db() as conn:
        with conn.cursor() as cur:
            ensure_alert_table(cur)
            cur.execute(
                """
                SELECT 1
                FROM crawler_health_alerts
                WHERE alert_key = %s
                  AND status = 'open'
                """,
                (alert_key,),
            )
            return cur.fetchone() is not None


def alert_notify_due(alert_key: str, repeat_minutes: int) -> bool:
    with connect_db() as conn:
        with conn.cursor() as cur:
            ensure_alert_table(cur)
            cur.execute(
                """
                SELECT last_notified_at IS NULL
                    OR last_notified_at <= NOW() - (%s * INTERVAL '1 minute')
                FROM crawler_health_alerts
                WHERE alert_key = %s
                  AND status = 'open'
                """,
                (repeat_minutes, alert_key),
            )
            row = cur.fetchone()
            return bool(row and row[0])


def mark_alert_notified(alert_key: str) -> None:
    with connect_db() as conn:
        with conn.cursor() as cur:
            ensure_alert_table(cur)
            cur.execute(
                """
                UPDATE crawler_health_alerts
                SET last_notified_at = NOW(),
                    updated_at = NOW()
                WHERE alert_key = %s
                  AND status = 'open'
                """,
                (alert_key,),
            )


def record_open_alert_fallback(
    state: dict,
    alert_key: str,
    message: str,
    now: datetime,
) -> None:
    state["open_alert_key"] = alert_key
    state["open_alert_message"] = message
    state["open_alert_at"] = state.get("open_alert_at") or now.isoformat()
    state["last_detected_at"] = now.isoformat()


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
    parser.add_argument("--repeat-minutes", type=int, default=30)
    parser.add_argument("--cooldown-minutes", type=int, default=180, help=argparse.SUPPRESS)
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--resolve", action="store_true", help="열린 FM코리아 쿠키 알림을 처리 완료로 닫기")
    parser.add_argument("--resolution-note", default="쿠키 갱신 처리 완료")
    args = parser.parse_args()

    now = datetime.now()
    state = load_state(args.state_path)

    if args.resolve:
        try:
            resolved = resolve_alert(DEFAULT_ALERT_KEY, args.resolution_note)
        except psycopg2.Error as exc:
            print(f"FM코리아 알림 처리 완료 실패: DB 오류 - {exc}")
            return 1
        state.pop("open_alert_key", None)
        state.pop("open_alert_message", None)
        state.pop("open_alert_at", None)
        save_state(args.state_path, state)
        if resolved:
            print("FM코리아 알림 처리 완료: 열린 쿠키 갱신 알림을 닫았습니다.")
        else:
            print("FM코리아 알림 처리 완료: 열린 알림이 없습니다.")
        return 0

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
        details = {
            "latest_status": latest.status,
            "latest_seen_at": latest.timestamp.isoformat(),
            "consecutive_430_threshold": args.consecutive_430,
        }
        try:
            open_or_update_alert(
                DEFAULT_ALERT_KEY,
                "fmkorea",
                "FM코리아 쿠키 갱신 필요",
                message,
                details,
            )
            notify_due = alert_notify_due(DEFAULT_ALERT_KEY, args.repeat_minutes)
        except psycopg2.Error as exc:
            print(f"FM코리아 경고: DB 알림 기록 실패, 상태 파일로 대체 - {exc}")
            record_open_alert_fallback(state, DEFAULT_ALERT_KEY, message, now)
            notify_due = should_notify(state, now, args.repeat_minutes)

        if notify_due:
            if not args.no_notify:
                send_macos_notification("Human Index", message)
            state["last_alert_at"] = now.isoformat()
            try:
                mark_alert_notified(DEFAULT_ALERT_KEY)
            except psycopg2.Error:
                pass
            print(f"FM코리아 경고: {message}")
        else:
            print("FM코리아 경고: 430 연속 감지, 반복 알림 주기 전이라 알림 생략")
        save_state(args.state_path, state)
        return 0

    if latest.status == 200:
        state["last_healthy_at"] = latest.timestamp.isoformat()
        try:
            if has_open_alert(DEFAULT_ALERT_KEY):
                if alert_notify_due(DEFAULT_ALERT_KEY, args.repeat_minutes):
                    message = (
                        "FM코리아 응답은 정상화됐지만 쿠키 갱신 알림이 아직 열려 있습니다. "
                        "확인 후 처리 완료를 실행하세요."
                    )
                    if not args.no_notify:
                        send_macos_notification("Human Index", message)
                    mark_alert_notified(DEFAULT_ALERT_KEY)
                    print(f"FM코리아 알림 미처리: {message}")
                    save_state(args.state_path, state)
                    return 0
        except psycopg2.Error as exc:
            print(f"FM코리아 상태 정상, DB 알림 확인 실패: {exc}")
    save_state(args.state_path, state)
    print(f"FM코리아 상태 정상: 최신 status={latest.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
