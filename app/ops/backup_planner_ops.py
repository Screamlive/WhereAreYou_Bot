from __future__ import annotations

from pathlib import Path

from app.ops.common import PYTHON_BIN, ROOT_DIR
from app.ops.systemd_units import BACKUP_SERVICE_UNIT, BACKUP_TIMER_UNIT, run_systemctl, write_unit


def _parse_hhmm(value: str) -> tuple[int, int]:
    raw = value.strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("Формат времени должен быть HH:MM.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("Часы и минуты должны быть числами.") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Некорректное время. Допустимо HH=00..23 и MM=00..59.")
    return hour, minute


def _render_backup_service(retain: int) -> str:
    if retain < 1:
        raise ValueError("retain должен быть >= 1.")
    return f"""
[Unit]
Description=Telegram bot backup + verify + prune
After=network.target

[Service]
Type=oneshot
WorkingDirectory={ROOT_DIR}
ExecStart={PYTHON_BIN} {ROOT_DIR / "manage.py"} backup create
ExecStartPost={PYTHON_BIN} {ROOT_DIR / "manage.py"} backup verify
ExecStartPost={PYTHON_BIN} {ROOT_DIR / "manage.py"} backup prune --retain {retain}
"""


def _render_backup_timer(hour: int, minute: int) -> str:
    return f"""
[Unit]
Description=Daily Telegram bot backup timer

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true
RandomizedDelaySec=2m
Unit={BACKUP_SERVICE_UNIT}

[Install]
WantedBy=timers.target
"""


def install_backup_timer(
    time_hhmm: str = "03:30",
    retain: int = 20,
    scope: str = "user",
) -> tuple[Path, Path]:
    hour, minute = _parse_hhmm(time_hhmm)
    service_path = write_unit(BACKUP_SERVICE_UNIT, _render_backup_service(retain), scope)
    timer_path = write_unit(BACKUP_TIMER_UNIT, _render_backup_timer(hour, minute), scope)

    run_systemctl(scope, ["daemon-reload"])
    run_systemctl(scope, ["enable", "--now", BACKUP_TIMER_UNIT])
    return service_path, timer_path


def disable_backup_timer(scope: str = "user") -> None:
    run_systemctl(scope, ["disable", "--now", BACKUP_TIMER_UNIT])
    run_systemctl(scope, ["daemon-reload"])


def run_backup_now(scope: str = "user") -> None:
    run_systemctl(scope, ["start", BACKUP_SERVICE_UNIT])


def status_backup_timer(scope: str = "user") -> None:
    run_systemctl(scope, ["status", BACKUP_TIMER_UNIT, "--no-pager"])

