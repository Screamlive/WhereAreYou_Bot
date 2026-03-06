from __future__ import annotations

import shutil
import subprocess

from app.ops import backup_ops
from app.ops.common import colorize, run_cmd
from app.ops.service_ops import SERVICE_TARGETS, has_systemctl

PROCESS_PATTERNS = {
    "bot": r"python(3)? .*bot\.py|python(3)? .*app\.entrypoints\.bot_main",
    "webapp": r"python(3)? .*webapp_api\.py|python(3)? .*app\.entrypoints\.webapp_main",
    "notifications": r"python(3)? .*notifications\.py|python(3)? .*app\.entrypoints\.notifications_main",
    "cloudflared": r"cloudflared",
}


def _get_matching_processes(pattern: str) -> list[str]:
    if shutil.which("pgrep") is None:
        return []
    result = run_cmd(["pgrep", "-af", pattern], capture=True)
    if result.returncode != 0 or not result.stdout:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _get_unit_state(unit: str, scope: str) -> tuple[str, str]:
    base = ["systemctl"]
    if scope == "user":
        base.append("--user")

    active = subprocess.run(
        [*base, "is-active", unit],
        cwd=None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    enabled = subprocess.run(
        [*base, "is-enabled", unit],
        cwd=None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    active_text = (active.stdout or "").strip() or "unknown"
    enabled_text = (enabled.stdout or "").strip() or "unknown"
    return active_text, enabled_text


def collect_process_statuses() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name, pattern in PROCESS_PATTERNS.items():
        result[name] = _get_matching_processes(pattern)
    return result


def collect_systemd_statuses() -> dict[str, tuple[str, str, str, str]]:
    result: dict[str, tuple[str, str, str, str]] = {}
    if not has_systemctl():
        return result
    for target, (unit, default_scope) in SERVICE_TARGETS.items():
        active, enabled = _get_unit_state(unit, default_scope)
        result[target] = (active, enabled, unit, default_scope)
    return result


def _color_for_active(value: str) -> str:
    if value == "active":
        return "green"
    if value in {"inactive", "failed", "dead", "unknown"}:
        return "red"
    return "yellow"


def _color_for_enabled(value: str) -> str:
    if value == "enabled":
        return "green"
    if value in {"disabled", "masked", "unknown"}:
        return "red"
    return "yellow"


def print_status() -> int:
    print("== Процессы ==")
    process_statuses = collect_process_statuses()
    for name, lines in process_statuses.items():
        if not lines:
            print(f"- {name}: {colorize('не запущен', 'red')}")
            continue
        print(f"- {name}: {colorize(f'{len(lines)} процесс(ов)', 'green')}")
        for line in lines[:3]:
            print(f"    {line}")
        if len(lines) > 3:
            print("    ...")

    print("\n== systemd ==")
    if not has_systemctl():
        print("- systemctl не найден")
    else:
        systemd_statuses = collect_systemd_statuses()
        for target, (active, enabled, unit, default_scope) in systemd_statuses.items():
            active_colored = colorize(active, _color_for_active(active))
            enabled_colored = colorize(enabled, _color_for_enabled(enabled))
            print(
                f"- {target} ({default_scope}:{unit}): "
                f"active={active_colored}, enabled={enabled_colored}"
            )

    print("\n== backup/disk ==")
    disk_state, disk_message, _free, _total, _free_percent = backup_ops.disk_guardrail_status()
    disk_color = "green"
    if disk_state == "warning":
        disk_color = "yellow"
    elif disk_state == "critical":
        disk_color = "red"
    print(f"- disk: {colorize(disk_state.upper(), disk_color)} ({disk_message})")

    return 0
