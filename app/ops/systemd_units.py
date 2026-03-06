from __future__ import annotations

import shutil
from pathlib import Path

from app.ops.common import run_cmd

BACKUP_SERVICE_UNIT = "telegram_bot_backup.service"
BACKUP_TIMER_UNIT = "telegram_bot_backup.timer"
MONITOR_SERVICE_UNIT = "telegram_bot_monitor.service"
MONITOR_TIMER_UNIT = "telegram_bot_monitor.timer"
EVENT_ALERT_TEMPLATE_UNIT = "telegram_bot_event_alert@.service"
EVENT_ALERT_DROPIN_NAME = "90-telegram-event-alert.conf"


def has_systemctl() -> bool:
    return shutil.which("systemctl") is not None


def resolve_scope(scope: str | None) -> str:
    value = (scope or "user").strip().lower()
    if value not in {"system", "user"}:
        raise ValueError("scope должен быть 'system' или 'user'.")
    return value


def unit_dir(scope: str) -> Path:
    actual_scope = resolve_scope(scope)
    if actual_scope == "user":
        return Path.home() / ".config" / "systemd" / "user"
    return Path("/etc/systemd/system")


def write_unit(unit_name: str, content: str, scope: str) -> Path:
    folder = unit_dir(scope)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / unit_name
    target.write_text(content.rstrip() + "\n", encoding="utf-8")
    return target


def run_systemctl(scope: str, args: list[str]):
    if not has_systemctl():
        raise RuntimeError("systemctl не найден в системе.")
    actual_scope = resolve_scope(scope)
    cmd = ["systemctl"]
    if actual_scope == "user":
        cmd.append("--user")
    cmd.extend(args)
    return run_cmd(cmd, capture=False)
