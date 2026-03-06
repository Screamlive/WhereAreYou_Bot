from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.ops import alerts_ops, backup_ops, status_ops
from app.ops.common import PYTHON_BIN, ROOT_DIR, colorize
from app.ops.service_ops import SERVICE_TARGETS
from app.ops.systemd_units import (
    BACKUP_SERVICE_UNIT,
    EVENT_ALERT_DROPIN_NAME,
    EVENT_ALERT_TEMPLATE_UNIT,
    MONITOR_SERVICE_UNIT,
    MONITOR_TIMER_UNIT,
    has_systemctl,
    resolve_scope,
    run_systemctl,
    unit_dir,
    write_unit,
)

MONITOR_STATE_FILE = ROOT_DIR / ".runtime" / "monitor_state.json"


@dataclass(frozen=True)
class Incident:
    severity: str  # critical | warning
    source: str
    message: str


def _render_event_alert_template(scope: str) -> str:
    actual_scope = resolve_scope(scope)
    return f"""
[Unit]
Description=Telegram event alert for failed unit %i
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={ROOT_DIR}
ExecStart={PYTHON_BIN} {ROOT_DIR / "manage.py"} alerts event --unit %i --scope {actual_scope}
"""


def _event_units_for_scope(scope: str) -> list[str]:
    actual_scope = resolve_scope(scope)
    result: list[str] = []
    for unit_name, unit_scope in SERVICE_TARGETS.values():
        if unit_scope == actual_scope and unit_name.endswith(".service"):
            result.append(unit_name)
    if actual_scope == "user":
        for extra in (BACKUP_SERVICE_UNIT, MONITOR_SERVICE_UNIT):
            if extra not in result:
                result.append(extra)
    return sorted(set(result))


def _parse_units_argument(units_csv: str | None, scope: str) -> list[str]:
    if not units_csv:
        return _event_units_for_scope(scope)
    values = [item.strip() for item in units_csv.split(",") if item.strip()]
    if not values:
        raise ValueError("Список units пустой.")
    units: list[str] = []
    alias_map = SERVICE_TARGETS
    for value in values:
        if value in alias_map:
            unit_name, unit_scope = alias_map[value]
            if unit_scope != resolve_scope(scope):
                raise ValueError(f"Unit alias {value} имеет scope {unit_scope}, а выбран {scope}.")
            units.append(unit_name)
            continue
        if not value.endswith(".service"):
            raise ValueError(f"Поддерживаются только service-unit: {value}")
        units.append(value)
    return sorted(set(units))


def _event_dropin_path(unit_name: str, scope: str) -> Path:
    base = unit_dir(scope)
    return base / f"{unit_name}.d" / EVENT_ALERT_DROPIN_NAME


def _write_event_dropin(unit_name: str, scope: str) -> Path:
    target = _event_dropin_path(unit_name, scope)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "[Unit]\n"
        f"OnFailure={EVENT_ALERT_TEMPLATE_UNIT.replace('@.service', '')}@%n.service\n",
        encoding="utf-8",
    )
    return target


def install_event_alerts(scope: str = "user", units_csv: str | None = None) -> tuple[Path, list[Path]]:
    actual_scope = resolve_scope(scope)
    template_path = write_unit(EVENT_ALERT_TEMPLATE_UNIT, _render_event_alert_template(actual_scope), actual_scope)
    units = _parse_units_argument(units_csv, actual_scope)
    dropins = [_write_event_dropin(unit_name, actual_scope) for unit_name in units]
    run_systemctl(actual_scope, ["daemon-reload"])
    return template_path, dropins


def disable_event_alerts(scope: str = "user", units_csv: str | None = None) -> list[Path]:
    actual_scope = resolve_scope(scope)
    units = _parse_units_argument(units_csv, actual_scope)
    removed: list[Path] = []
    for unit_name in units:
        path = _event_dropin_path(unit_name, actual_scope)
        if path.exists():
            path.unlink()
            removed.append(path)
        # remove empty drop-in directory if no files remain
        if path.parent.exists() and not any(path.parent.iterdir()):
            path.parent.rmdir()
    run_systemctl(actual_scope, ["daemon-reload"])
    return removed


def event_alerts_status(scope: str = "user", units_csv: str | None = None) -> list[tuple[str, bool, str]]:
    actual_scope = resolve_scope(scope)
    units = _parse_units_argument(units_csv, actual_scope)
    result: list[tuple[str, bool, str]] = []
    for unit_name in units:
        path = _event_dropin_path(unit_name, actual_scope)
        enabled = path.exists()
        result.append((unit_name, enabled, str(path)))
    return result


def _severity_color(value: str) -> str:
    if value == "critical":
        return "red"
    return "yellow"


def _is_failed_unit(unit_name: str, scope: str = "user") -> bool:
    if not has_systemctl():
        return False
    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    cmd.extend(["is-failed", unit_name])
    result = subprocess.run(
        cmd,
        cwd=None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    value = (result.stdout or "").strip()
    return value == "failed"


def collect_incidents() -> list[Incident]:
    incidents: list[Incident] = []
    processes = status_ops.collect_process_statuses()
    systemd_status = status_ops.collect_systemd_statuses()

    for target in ("bot", "webapp"):
        process_ok = bool(processes.get(target))
        active, _enabled, _unit, _scope = systemd_status.get(target, ("unknown", "unknown", "", ""))
        service_ok = active == "active"
        if not (process_ok or service_ok):
            incidents.append(
                Incident(
                    severity="critical",
                    source=target,
                    message="Компонент не запущен (нет процесса и не active в systemd).",
                )
            )

    notify_timer = systemd_status.get("notify-timer")
    if notify_timer and notify_timer[0] != "active":
        incidents.append(
            Incident(
                severity="warning",
                source="notify-timer",
                message=f"timer имеет состояние {notify_timer[0]} (ожидалось active).",
            )
        )

    disk_state, disk_message, _free, _total, _free_percent = backup_ops.disk_guardrail_status()
    if disk_state in {"warning", "critical"}:
        incidents.append(
            Incident(
                severity=disk_state,
                source="disk",
                message=disk_message,
            )
        )

    if _is_failed_unit(BACKUP_SERVICE_UNIT, scope="user"):
        incidents.append(
            Incident(
                severity="critical",
                source="backup-service",
                message=f"{BACKUP_SERVICE_UNIT} в состоянии failed.",
            )
        )

    if _is_failed_unit(MONITOR_SERVICE_UNIT, scope="user"):
        incidents.append(
            Incident(
                severity="warning",
                source="monitor-service",
                message=f"{MONITOR_SERVICE_UNIT} в состоянии failed.",
            )
        )

    return incidents


def _incident_payload(incidents: list[Incident]) -> str:
    lines = [f"- [{item.severity}] {item.source}: {item.message}" for item in incidents]
    return "\n".join(lines)


def _incidents_hash(incidents: list[Incident]) -> str:
    payload = _incident_payload(incidents)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_state() -> dict[str, str]:
    if not MONITOR_STATE_FILE.exists():
        return {}
    try:
        return json.loads(MONITOR_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(state: dict[str, str]) -> None:
    MONITOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MONITOR_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _send_notifications_if_needed(incidents: list[Incident]) -> None:
    contacts = alerts_ops.load_contacts()
    if not contacts:
        print(colorize("Контакты техадминов не заданы: уведомления пропущены.", "yellow"))
        return

    state = _load_state()
    previous_hash = state.get("last_incidents_hash", "")
    previous_mode = state.get("mode", "")

    if incidents:
        current_hash = _incidents_hash(incidents)
        if current_hash == previous_hash and previous_mode == "incident":
            print("Уведомление не отправлено: инциденты не изменились.")
            return

        text = "Мониторинг: обнаружены инциденты.\n\n" + _incident_payload(incidents)
        sent, failures = alerts_ops.send_alert(text, contacts)
        print(f"Уведомления отправлены: {sent}, ошибок: {len(failures)}")
        _save_state({"mode": "incident", "last_incidents_hash": current_hash})
        return

    if previous_mode == "incident":
        sent, failures = alerts_ops.send_alert("Мониторинг: инциденты устранены, статус OK.", contacts)
        print(f"Уведомление о восстановлении отправлено: {sent}, ошибок: {len(failures)}")
    _save_state({"mode": "ok", "last_incidents_hash": ""})


def run_monitor_check(notify: bool = False) -> int:
    incidents = collect_incidents()
    if not incidents:
        print(colorize("Monitor: OK (инциденты не обнаружены).", "green"))
        if notify:
            _send_notifications_if_needed([])
        return 0

    print("Monitor: обнаружены инциденты:")
    for item in incidents:
        sev = colorize(item.severity.upper(), _severity_color(item.severity))
        print(f"- [{sev}] {item.source}: {item.message}")

    if notify:
        _send_notifications_if_needed(incidents)

    has_critical = any(item.severity == "critical" for item in incidents)
    return 2 if has_critical else 1


def _render_monitor_service() -> str:
    return f"""
[Unit]
Description=Telegram bot monitor check with notifications
After=network.target

[Service]
Type=oneshot
WorkingDirectory={ROOT_DIR}
ExecStart={PYTHON_BIN} {ROOT_DIR / "manage.py"} monitor check --notify
"""


def _render_monitor_timer(interval_min: int) -> str:
    if interval_min < 1:
        raise ValueError("interval_min должен быть >= 1.")
    return f"""
[Unit]
Description=Telegram bot monitor timer

[Timer]
OnBootSec=2m
OnUnitActiveSec={interval_min}m
Persistent=true
Unit={MONITOR_SERVICE_UNIT}

[Install]
WantedBy=timers.target
"""


def install_monitor_timer(interval_min: int = 10, scope: str = "user") -> tuple[Path, Path]:
    service_path = write_unit(MONITOR_SERVICE_UNIT, _render_monitor_service(), scope)
    timer_path = write_unit(MONITOR_TIMER_UNIT, _render_monitor_timer(interval_min), scope)
    run_systemctl(scope, ["daemon-reload"])
    run_systemctl(scope, ["enable", "--now", MONITOR_TIMER_UNIT])
    return service_path, timer_path


def disable_monitor_timer(scope: str = "user") -> None:
    run_systemctl(scope, ["disable", "--now", MONITOR_TIMER_UNIT])
    run_systemctl(scope, ["daemon-reload"])


def run_monitor_now(scope: str = "user") -> None:
    run_systemctl(scope, ["start", MONITOR_SERVICE_UNIT])


def status_monitor_timer(scope: str = "user") -> None:
    run_systemctl(scope, ["status", MONITOR_TIMER_UNIT, "--no-pager"])
