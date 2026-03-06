from __future__ import annotations

import argparse
from pathlib import Path

from app.ops import (
    alerts_ops,
    backup_ops,
    backup_planner_ops,
    broadcast_ops,
    governance_ops,
    menu,
    monitor_ops,
    run_ops,
    service_ops,
    smoke_ops,
    status_ops,
)
from app.ops.common import colorize, human_bytes
from app.repositories.users_repo import get_all_users


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Операционная CLI-панель управления компонентами бота.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("menu", help="Интерактивное текстовое меню.")
    subparsers.add_parser("status", help="Показать статус процессов и systemd-юнитов.")

    run_parser = subparsers.add_parser("run", help="Запуск/остановка локальных компонентов (без systemd).")
    run_parser.add_argument("component", choices=sorted(run_ops.RUN_COMPONENTS.keys()))
    run_parser.add_argument("--mode", choices=["foreground", "background"], default="foreground")
    run_parser.add_argument("--action", choices=["start", "stop", "status"], default="start")
    run_parser.add_argument("--force", action="store_true", help="Для stop: принудительный SIGKILL после таймаута.")

    service_parser = subparsers.add_parser("service", help="Управление systemd service/timer.")
    service_parser.add_argument("target", choices=sorted(service_ops.SERVICE_TARGETS.keys()))
    service_parser.add_argument("action", choices=sorted(service_ops.SERVICE_ACTIONS))
    service_parser.add_argument("--scope", choices=["system", "user"], default=None)

    smoke_parser = subparsers.add_parser("smoke", help="Быстрый smoke-check WebApp endpoint.")
    smoke_parser.add_argument("--url", default=None, help="Базовый URL WebApp (например, https://example/webapp).")

    backup_parser = subparsers.add_parser("backup", help="Операции с backup БД.")
    backup_parser.add_argument(
        "action",
        choices=[
            "create",
            "list",
            "verify",
            "restore",
            "prune",
            "usage",
            "schedule-enable",
            "schedule-disable",
            "schedule-status",
            "schedule-run",
        ],
    )
    backup_parser.add_argument("--path", default=None, help="Путь к backup-файлу для verify/restore.")
    backup_parser.add_argument("--retain", type=int, default=20, help="Сколько последних backup хранить при prune.")
    backup_parser.add_argument("--time", default="03:30", help="Время запуска backup timer в формате HH:MM.")
    backup_parser.add_argument("--scope", choices=["system", "user"], default="user")

    governance_parser = subparsers.add_parser("governance", help="Проверки release-governance.")
    governance_parser.add_argument("action", choices=["checks", "checklist"])
    governance_parser.add_argument("--branch", default="main")

    broadcast_parser = subparsers.add_parser("broadcast", help="Сервисная рассылка.")
    broadcast_parser.add_argument("--audience", required=True, help="all|approved|group:<id>|superadmins|group_admins")
    source_group = broadcast_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--text")
    source_group.add_argument("--file")
    source_group.add_argument(
        "--changelog-latest",
        nargs="?",
        const="CHANGELOG.md",
        metavar="PATH",
        help="Отправить верхний блок changelog (по умолчанию CHANGELOG.md).",
    )
    broadcast_parser.add_argument("--limit", type=int, default=None)
    broadcast_parser.add_argument("--delay", type=float, default=0.08)
    broadcast_parser.add_argument("--dry-run", action="store_true")
    broadcast_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Требуется для реальной отправки (без --dry-run).",
    )

    alerts_parser = subparsers.add_parser("alerts", help="Тех-уведомления и контакты операторов.")
    alerts_subparsers = alerts_parser.add_subparsers(dest="alerts_command")

    alerts_contacts = alerts_subparsers.add_parser("contacts", help="Управление контактами техадминов.")
    alerts_contacts.add_argument("action", choices=["list", "add", "remove"])
    alerts_contacts.add_argument("--id", type=int, default=None, help="Telegram ID техадмина.")

    alerts_test = alerts_subparsers.add_parser("test", help="Отправить тестовое тех-уведомление.")
    alerts_test.add_argument("--message", default="Тестовое уведомление от manage.py")

    alerts_event = alerts_subparsers.add_parser("event", help="Служебная отправка по systemd OnFailure.")
    alerts_event.add_argument("--unit", required=True, help="Имя unit, переданное из OnFailure (%i).")
    alerts_event.add_argument("--scope", choices=["system", "user"], default="user")

    monitor_parser = subparsers.add_parser("monitor", help="Мониторинг компонентов и тех-уведомления.")
    monitor_parser.add_argument(
        "action",
        choices=[
            "check",
            "schedule-enable",
            "schedule-disable",
            "schedule-status",
            "schedule-run",
            "events-enable",
            "events-disable",
            "events-status",
        ],
    )
    monitor_parser.add_argument("--notify", action="store_true", help="Для check: отправлять уведомления техадминам.")
    monitor_parser.add_argument("--scope", choices=["system", "user"], default="user")
    monitor_parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Интервал monitor timer в минутах (для schedule-enable).",
    )
    monitor_parser.add_argument(
        "--units",
        default=None,
        help="CSV список service-unit или alias (например: bot,webapp). По умолчанию — рекомендуемый набор для scope.",
    )

    return parser


def _run_backup(action: str, path: str | None, retain: int, time_hhmm: str, scope: str) -> int:
    if action == "create":
        created = backup_ops.create_backup()
        print(f"Backup создан: {created}")
        return 0

    if action == "list":
        backups = backup_ops.list_backups()
        if not backups:
            print("Backup-файлы не найдены.")
            return 0
        print("Backup-файлы:")
        for idx, backup in enumerate(backups, start=1):
            print(f"{idx}) {backup}")
        return 0

    if action == "usage":
        disk_state, disk_message, free, total, free_percent = backup_ops.disk_guardrail_status()
        color = "green" if disk_state == "ok" else ("yellow" if disk_state == "warning" else "red")
        print(f"Свободно: {human_bytes(free)} из {human_bytes(total)} ({colorize(f'{free_percent:.1f}%', color)})")
        print(f"Guardrail: {disk_message}")
        return 0

    if action == "verify":
        target = Path(path).expanduser() if path else None
        checked, is_ok, result = backup_ops.verify_backup(target)
        status = colorize("OK", "green") if is_ok else colorize("FAIL", "red")
        print(f"Проверка: {checked}")
        print(f"PRAGMA integrity_check: {result}")
        print(f"Статус: {status}")
        return 0 if is_ok else 1

    if action == "restore":
        if not path:
            print("Ошибка: для restore нужен --path <backup.db>.")
            return 2
        target = Path(path).expanduser()
        restored, safety = backup_ops.restore_backup(target)
        print(f"Восстановлено в: {restored}")
        if safety:
            print(f"Перед восстановлением создан safety backup: {safety}")
        return 0

    if action == "schedule-enable":
        if retain < 1:
            print("Ошибка: --retain должен быть >= 1")
            return 2
        service_path, timer_path = backup_planner_ops.install_backup_timer(
            time_hhmm=time_hhmm,
            retain=retain,
            scope=scope,
        )
        print(f"Backup scheduler включен ({scope}).")
        print(f"Service: {service_path}")
        print(f"Timer:   {timer_path}")
        return 0

    if action == "schedule-disable":
        backup_planner_ops.disable_backup_timer(scope=scope)
        print(f"Backup scheduler отключен ({scope}).")
        return 0

    if action == "schedule-status":
        backup_planner_ops.status_backup_timer(scope=scope)
        return 0

    if action == "schedule-run":
        backup_planner_ops.run_backup_now(scope=scope)
        print(f"Backup job запущен вручную ({scope}).")
        return 0

    raise ValueError(f"Неизвестное действие backup: {action}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None or args.command == "menu":
        return menu.run_interactive_menu()

    if args.command == "status":
        return status_ops.print_status()

    if args.command == "run":
        if args.action == "status":
            print(run_ops.format_component_status_line(args.component))
            return 0
        if args.action == "stop":
            stopped = run_ops.stop_component_background(args.component, force=args.force)
            if stopped:
                print(f"{args.component}: остановлен")
            else:
                print(f"{args.component}: не запущен")
            return 0

        if args.mode == "background":
            pid, log_path = run_ops.start_component_background(args.component)
            print(f"{args.component}: запущен в фоне (PID {pid})")
            print(f"Лог: {log_path}")
            return 0

        return run_ops.run_component_foreground(args.component)

    if args.command == "service":
        result = service_ops.run_service_action(args.target, args.action, args.scope)
        return result.returncode

    if args.command == "smoke":
        return smoke_ops.run_smoke(args.url)

    if args.command == "backup":
        if args.action == "prune":
            if args.retain < 1:
                print("Ошибка: --retain должен быть >= 1")
                return 2
            removed = backup_ops.prune_backups(args.retain)
            print(f"Удалено backup-файлов: {len(removed)}")
            for item in removed[:20]:
                print(f"- {item}")
            return 0
        return _run_backup(args.action, args.path, args.retain, args.time, args.scope)

    if args.command == "governance":
        if args.action == "checks":
            return governance_ops.print_governance_checks(branch=args.branch)
        return governance_ops.print_governance_checklist()

    if args.command == "broadcast":
        if args.limit is not None and args.limit < 1:
            print("Ошибка: --limit должен быть >= 1")
            return 2
        if args.delay < 0:
            print("Ошибка: --delay должен быть >= 0")
            return 2

        if not args.dry_run and not args.confirm:
            print("Ошибка: для реальной отправки укажите --confirm (или используйте --dry-run).")
            return 2

        return broadcast_ops.run_broadcast(
            audience=args.audience,
            text=args.text,
            file_path=args.file,
            changelog_latest=args.changelog_latest,
            limit=args.limit,
            delay=args.delay,
            dry_run=args.dry_run,
        )

    if args.command == "alerts":
        if args.alerts_command is None:
            parser.print_help()
            return 2
        if args.alerts_command == "contacts":
            if args.action == "list":
                contacts = alerts_ops.load_contacts()
                if not contacts:
                    print("Контакты техадминов не заданы.")
                    return 0
                users_by_id = {user_id: (fullname, username) for user_id, fullname, username in get_all_users()}
                print("Контакты техадминов:")
                for value in contacts:
                    fullname, username = users_by_id.get(value, (f"Пользователь {value}", ""))
                    marker = f"@{username}" if username else f"ID {value}"
                    print(f"- {fullname} ({marker})")
                return 0
            if args.id is None:
                if args.action == "remove":
                    contacts = alerts_ops.load_contacts()
                    if not contacts:
                        print("Техадмины не заданы.")
                    else:
                        users_by_id = {user_id: (fullname, username) for user_id, fullname, username in get_all_users()}
                        print("Текущие техадмины:")
                        for value in contacts:
                            fullname, username = users_by_id.get(value, (f"Пользователь {value}", ""))
                            marker = f"@{username}" if username else f"ID {value}"
                            print(f"- {fullname} ({marker})")
                print("Ошибка: для add/remove нужен --id <telegram_id>.")
                return 2
            if args.action == "add":
                contacts = alerts_ops.add_contact(args.id)
                print(f"Контакт добавлен. Всего: {len(contacts)}")
                return 0
            contacts = alerts_ops.remove_contact(args.id)
            print(f"Контакт удален. Всего: {len(contacts)}")
            return 0
        if args.alerts_command == "event":
            text = alerts_ops.build_event_alert_text(unit=args.unit, scope=args.scope)
            sent, failures = alerts_ops.send_alert(text)
            print(f"Event alert: отправлено {sent}, ошибок {len(failures)}")
            for chat_id, error in failures[:20]:
                print(f"- {chat_id}: {error}")
            return 0 if not failures else 1
        sent, failures = alerts_ops.send_alert(args.message)
        print(f"Отправлено: {sent}, ошибок: {len(failures)}")
        for chat_id, error in failures[:20]:
            print(f"- {chat_id}: {error}")
        return 0 if not failures else 1

    if args.command == "monitor":
        if args.action == "check":
            return monitor_ops.run_monitor_check(notify=args.notify)
        if args.action == "schedule-enable":
            if args.interval < 1:
                print("Ошибка: --interval должен быть >= 1.")
                return 2
            service_path, timer_path = monitor_ops.install_monitor_timer(
                interval_min=args.interval,
                scope=args.scope,
            )
            print(f"Monitor scheduler включен ({args.scope}).")
            print(f"Service: {service_path}")
            print(f"Timer:   {timer_path}")
            return 0
        if args.action == "schedule-disable":
            monitor_ops.disable_monitor_timer(scope=args.scope)
            print(f"Monitor scheduler отключен ({args.scope}).")
            return 0
        if args.action == "schedule-status":
            monitor_ops.status_monitor_timer(scope=args.scope)
            return 0
        if args.action == "events-enable":
            template_path, dropins = monitor_ops.install_event_alerts(scope=args.scope, units_csv=args.units)
            print(f"Event alerts включены ({args.scope}).")
            print(f"Template: {template_path}")
            print("Drop-ins:")
            for item in dropins:
                print(f"- {item}")
            return 0
        if args.action == "events-disable":
            removed = monitor_ops.disable_event_alerts(scope=args.scope, units_csv=args.units)
            print(f"Event alerts отключены ({args.scope}), удалено drop-in: {len(removed)}")
            for item in removed:
                print(f"- {item}")
            return 0
        if args.action == "events-status":
            rows = monitor_ops.event_alerts_status(scope=args.scope, units_csv=args.units)
            print(f"Event alerts status ({args.scope}):")
            for unit_name, enabled, path in rows:
                state = "ENABLED" if enabled else "DISABLED"
                print(f"- {unit_name}: {state} ({path})")
            return 0
        monitor_ops.run_monitor_now(scope=args.scope)
        print(f"Monitor job запущен вручную ({args.scope}).")
        return 0

    parser.print_help()
    return 2
