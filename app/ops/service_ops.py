from __future__ import annotations

import shutil

from app.ops.common import run_cmd

SERVICE_TARGETS = {
    "bot": ("telegram_bot.service", "user"),
    "webapp": ("telegram_webapp.service", "user"),
    "notify-service": ("telegram_bot_notify.service", "user"),
    "notify-timer": ("telegram_bot_notify.timer", "user"),
    "backup-service": ("telegram_bot_backup.service", "user"),
    "backup-timer": ("telegram_bot_backup.timer", "user"),
    "monitor-service": ("telegram_bot_monitor.service", "user"),
    "monitor-timer": ("telegram_bot_monitor.timer", "user"),
    "cloudflared": ("cloudflared.service", "system"),
    "nginx": ("nginx.service", "system"),
}

SERVICE_ACTIONS = {
    "status",
    "start",
    "stop",
    "restart",
    "enable",
    "disable",
}


def has_systemctl() -> bool:
    return shutil.which("systemctl") is not None


def resolve_target(target: str) -> tuple[str, str]:
    if target in SERVICE_TARGETS:
        return SERVICE_TARGETS[target]
    if target.endswith(".service") or target.endswith(".timer"):
        return target, "system"
    raise ValueError(f"Неизвестная цель сервиса: {target}")


def run_service_action(target: str, action: str, scope: str | None = None):
    if action not in SERVICE_ACTIONS:
        raise ValueError(f"Неизвестное действие: {action}")
    if not has_systemctl():
        raise RuntimeError("systemctl не найден в системе.")

    unit, default_scope = resolve_target(target)
    actual_scope = (scope or default_scope).strip().lower()
    if actual_scope not in {"system", "user"}:
        raise ValueError("scope должен быть 'system' или 'user'.")

    prefix = ["systemctl"]
    if actual_scope == "user":
        prefix.append("--user")

    if action == "status":
        cmd = [*prefix, "status", unit, "--no-pager"]
    else:
        cmd = [*prefix, action, unit]

    return run_cmd(cmd, capture=False)
