from __future__ import annotations

from pathlib import Path

from app.ops import (
    alerts_ops,
    backup_ops,
    backup_planner_ops,
    broadcast_ops,
    monitor_ops,
    run_ops,
    service_ops,
    smoke_ops,
    status_ops,
)
from app.ops.common import clear_terminal, colorize, human_bytes
from app.repositories.groups_repo import list_all_groups
from app.repositories.users_repo import get_all_users
from database import init_db

MENU_BACK = "__back__"


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _ask_optional_int(prompt: str) -> int | None:
    while True:
        raw = _ask(prompt)
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            print(colorize("Нужно ввести целое число.", "red"))
            continue
        if value < 1:
            print(colorize("Число должно быть >= 1.", "red"))
            continue
        return value


def _ask_optional_float(prompt: str, default: float) -> float:
    while True:
        raw = _ask(prompt)
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            print(colorize("Нужно ввести число.", "red"))
            continue
        if value < 0:
            print(colorize("Число должно быть >= 0.", "red"))
            continue
        return value


def _username_or_id(username: str, user_id: int) -> str:
    value = (username or "").strip()
    return f"@{value}" if value else f"ID {user_id}"


def _choose_user_from_directory(
    title: str,
    users: list[tuple[int, str, str]],
) -> int | None:
    if not users:
        raise ValueError("Нет пользователей для выбора.")
    sorted_users = sorted(users, key=lambda item: (item[1] or "").lower())
    items = [
        (str(user_id), f"{fullname} ({_username_or_id(username, user_id)})")
        for user_id, fullname, username in sorted_users
    ]
    selected = _choose(title, items, allow_back=True, back_label="Отмена")
    if selected == MENU_BACK:
        return None
    return int(selected)


def _confirm(prompt: str, default: bool = False) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    yes_values = {"y", "yes", "д", "да"}
    no_values = {"n", "no", "н", "нет"}
    while True:
        raw = _ask(f"{prompt} {hint}: ").lower()
        if not raw:
            return default
        if raw in yes_values:
            return True
        if raw in no_values:
            return False
        print(colorize("Введите y/yes/д/да или n/no/н/нет.", "yellow"))


def _confirm_send() -> bool:
    print("\nДля подтверждения отправки введите SEND (или CANCEL для отмены)")
    while True:
        raw = _ask("Подтверждение: ")
        if raw == "SEND":
            return True
        if raw.upper() == "CANCEL" or raw == "":
            return False
        print(colorize("Введите SEND для отправки или CANCEL для отмены.", "yellow"))


def _choose(
    title: str,
    items: list[tuple[str, str]],
    allow_back: bool = False,
    back_label: str = "Вернуться в предыдущее меню",
) -> str:
    visible_items = list(items)
    if allow_back:
        visible_items.append((MENU_BACK, back_label))
    while True:
        print(f"\n{title}")
        for idx, (_value, label) in enumerate(visible_items, start=1):
            print(f"{idx}) {label}")
        raw = _ask("Выберите номер: ")
        try:
            idx = int(raw)
        except ValueError:
            print(colorize("Нужно ввести номер пункта.", "red"))
            continue
        if idx < 1 or idx > len(visible_items):
            print(colorize("Номер вне диапазона.", "red"))
            continue
        return visible_items[idx - 1][0]


def _pause() -> None:
    input("\nНажмите Enter для продолжения...")


def _broadcast_source_wizard() -> tuple[str | None, str | None, str | None] | None:
    mode = _choose(
        "Источник рассылки:",
        [
            ("changelog", "Актуальный блок CHANGELOG"),
            ("text", "Произвольный текст"),
            ("file", "Файл (.txt/.md)"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if mode == MENU_BACK:
        return None

    if mode == "changelog":
        path = _ask("Путь к CHANGELOG (Enter = CHANGELOG.md): ")
        return None, None, (path or "CHANGELOG.md")

    if mode == "file":
        file_path = broadcast_ops.resolve_existing_file(_ask("Путь к файлу: "))
        return None, file_path, None

    print("Введите текст сообщения. Для завершения введите одиночную точку '.' на новой строке.")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("Текст сообщения пустой.")
    return text, None, None


def _broadcast_audience_wizard() -> str | None:
    mode = _choose(
        "Аудитория рассылки:",
        [
            ("approved", "Одобренные пользователи"),
            ("all", "Все пользователи"),
            ("superadmins", "Суперадмины"),
            ("group_admins", "Админы групп"),
            ("group", "Конкретная группа"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if mode == MENU_BACK:
        return None

    if mode != "group":
        return mode

    init_db()
    groups = list_all_groups()
    if not groups:
        raise ValueError("Нет групп для выбора.")

    group_items = [(str(group_id), f"[{group_id}] {name}") for group_id, name in groups]
    group_id = _choose(
        "Выберите группу:",
        group_items,
        allow_back=True,
        back_label="Вернуться к выбору аудитории",
    )
    if group_id == MENU_BACK:
        return None
    return f"group:{group_id}"


def _menu_broadcast() -> None:
    print("\n=== Рассылка ===")
    source = _broadcast_source_wizard()
    if source is None:
        return
    text, file_path, changelog_latest = source
    audience = _broadcast_audience_wizard()
    if audience is None:
        return
    limit = _ask_optional_int("Лимит получателей (Enter = без лимита): ")
    delay = _ask_optional_float("Пауза между отправками, сек (Enter = 0.08): ", default=0.08)

    print("\n--- Предпросмотр (dry-run) ---")
    preview_code = broadcast_ops.preview_broadcast(
        audience=audience,
        text=text,
        file_path=file_path,
        changelog_latest=changelog_latest,
        limit=limit,
        delay=delay,
    )
    if preview_code != 0:
        print(colorize("Предпросмотр завершился с ошибкой. Отправка отменена.", "red"))
        return

    if not _confirm_send():
        print("Отправка отменена.")
        return

    print("\n--- Отправка ---")
    code = broadcast_ops.run_broadcast(
        audience=audience,
        text=text,
        file_path=file_path,
        changelog_latest=changelog_latest,
        limit=limit,
        delay=delay,
        dry_run=False,
    )
    if code == 0:
        print(colorize("Готово.", "green"))
    else:
        print(colorize(f"Рассылка завершилась с кодом {code}.", "red"))


def _menu_run_component() -> None:
    component = _choose(
        "Локальные компоненты (без systemd):",
        [
            ("bot", "Бот (bot.py)"),
            ("webapp", "WebApp API (webapp_api.py)"),
            ("notify-once", "Ежедневные уведомления разово (notifications.py)"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if component == MENU_BACK:
        return

    action = _choose(
        "Действие:",
        [
            ("bg-start", "Запустить в фоне"),
            ("bg-stop", "Остановить фоновый процесс"),
            ("bg-status", "Статус фонового процесса"),
            ("fg-start", "Запустить в текущем терминале"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if action == MENU_BACK:
        return

    if action == "bg-status":
        print(run_ops.format_component_status_line(component))
        return

    if action == "bg-stop":
        force = _confirm("Принудительно завершить, если не остановится по SIGTERM?", default=False)
        stopped = run_ops.stop_component_background(component, force=force)
        if stopped:
            print(colorize(f"{component}: остановлен", "green"))
        else:
            print(colorize(f"{component}: не запущен", "yellow"))
        return

    if action == "bg-start":
        pid, log_path = run_ops.start_component_background(component)
        print(colorize(f"{component}: запущен в фоне (PID {pid})", "green"))
        print(f"Лог: {log_path}")
        return

    print("Команда будет работать в текущем терминале до остановки процесса.")
    if not _confirm("Продолжить?", default=False):
        print("Отменено.")
        return
    run_ops.run_component_foreground(component)


def _menu_service() -> None:
    target = _choose(
        "Выберите сервис:",
        [
            ("bot", "bot -> telegram_bot.service"),
            ("webapp", "webapp -> telegram_webapp.service"),
            ("notify-service", "notify-service -> telegram_bot_notify.service"),
            ("notify-timer", "notify-timer -> telegram_bot_notify.timer"),
            ("backup-service", "backup-service -> telegram_bot_backup.service"),
            ("backup-timer", "backup-timer -> telegram_bot_backup.timer"),
            ("monitor-service", "monitor-service -> telegram_bot_monitor.service"),
            ("monitor-timer", "monitor-timer -> telegram_bot_monitor.timer"),
            ("cloudflared", "cloudflared -> cloudflared.service"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if target == MENU_BACK:
        return
    action = _choose(
        "Действие:",
        [
            ("status", "status"),
            ("start", "start"),
            ("stop", "stop"),
            ("restart", "restart"),
            ("enable", "enable"),
            ("disable", "disable"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if action == MENU_BACK:
        return

    default_scope = service_ops.SERVICE_TARGETS[target][1]
    scope = default_scope

    result = service_ops.run_service_action(target=target, action=action, scope=scope)
    if result.returncode != 0:
        print(colorize(f"Команда завершилась с кодом {result.returncode}", "red"))


def _menu_backup() -> None:
    disk_state, disk_message, free, total, free_percent = backup_ops.disk_guardrail_status()
    free_color = "green" if disk_state == "ok" else ("yellow" if disk_state == "warning" else "red")
    print(
        "\nСвободное место (том с backup): "
        f"{human_bytes(free)} / {human_bytes(total)} "
        f"({colorize(f'{free_percent:.1f}%', free_color)})"
    )
    print(f"Guardrail: {disk_message}")

    action = _choose(
        "Backup:",
        [
            ("create", "Создать backup"),
            ("list", "Список backup"),
            ("verify", "Проверить integrity (последний backup)"),
            ("restore", "Восстановить из backup"),
            ("prune", "Удалить старые backup по глубине хранения"),
            ("schedule-enable", "Включить backup scheduler (systemd timer)"),
            ("schedule-disable", "Отключить backup scheduler"),
            ("schedule-status", "Статус backup scheduler"),
            ("schedule-run", "Запустить backup job вручную"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if action == MENU_BACK:
        return

    if action == "create":
        path = backup_ops.create_backup()
        print(colorize(f"Backup создан: {path}", "green"))
        return

    if action == "list":
        backups = backup_ops.list_backups()
        if not backups:
            print("Backup-файлы не найдены.")
            return
        print("Найденные backup-файлы:")
        for idx, path in enumerate(backups, start=1):
            print(f"{idx}) {path}")
        return

    if action == "verify":
        path, is_ok, result = backup_ops.verify_backup(path=None)
        print(f"Файл: {path}")
        print(f"PRAGMA integrity_check: {result}")
        print(colorize("OK", "green") if is_ok else colorize("FAIL", "red"))
        return

    if action == "restore":
        path_value = _ask("Путь к backup-файлу: ")
        if not path_value:
            raise ValueError("Путь к файлу обязателен.")
        target = Path(path_value).expanduser()
        if not _confirm("Подтвердить восстановление БД из указанного backup?", default=False):
            print("Восстановление отменено.")
            return
        restored, safety = backup_ops.restore_backup(target)
        print(colorize(f"БД восстановлена: {restored}", "green"))
        if safety:
            print(f"Safety backup создан: {safety}")
        return

    if action == "schedule-enable":
        time_hhmm = _ask("Время запуска (HH:MM, Enter = 03:30): ") or "03:30"
        retain = _ask_optional_int("Сколько backup хранить (Enter = 20): ") or 20
        scope = "user"
        service_path, timer_path = backup_planner_ops.install_backup_timer(
            time_hhmm=time_hhmm,
            retain=retain,
            scope=scope,
        )
        print(colorize(f"Backup scheduler включен ({scope}).", "green"))
        print(f"Service: {service_path}")
        print(f"Timer: {timer_path}")
        return

    if action == "schedule-disable":
        scope = "user"
        backup_planner_ops.disable_backup_timer(scope=scope)
        print(colorize(f"Backup scheduler отключен ({scope}).", "green"))
        return

    if action == "schedule-status":
        scope = "user"
        backup_planner_ops.status_backup_timer(scope=scope)
        return

    if action == "schedule-run":
        scope = "user"
        backup_planner_ops.run_backup_now(scope=scope)
        print(colorize(f"Backup job запущен ({scope}).", "green"))
        return

    retain = _ask_optional_int("Сколько последних backup оставить (Enter = 20): ") or 20
    removed = backup_ops.prune_backups(retain)
    print(f"Удалено backup-файлов: {len(removed)}")


def _menu_monitor() -> None:
    action = _choose(
        "Мониторинг и тех-уведомления:",
        [
            ("check", "Проверить состояние (без уведомлений)"),
            ("check-notify", "Проверить состояние и отправить уведомления"),
            ("contacts-list", "Показать техадминов"),
            ("contacts-add", "Добавить техадмина"),
            ("contacts-remove", "Удалить техадмина"),
            ("alerts-test", "Отправить тестовое тех-уведомление"),
            ("schedule-enable", "Включить monitor scheduler (systemd timer)"),
            ("schedule-disable", "Отключить monitor scheduler"),
            ("schedule-status", "Статус monitor scheduler"),
            ("schedule-run", "Запустить monitor job вручную"),
            ("events-enable", "Включить событийные алерты (OnFailure)"),
            ("events-disable", "Отключить событийные алерты"),
            ("events-status", "Статус событийных алертов"),
        ],
        allow_back=True,
        back_label="Вернуться в главное меню",
    )
    if action == MENU_BACK:
        return

    if action == "check":
        monitor_ops.run_monitor_check(notify=False)
        return

    if action == "check-notify":
        monitor_ops.run_monitor_check(notify=True)
        return

    if action == "contacts-list":
        contacts = alerts_ops.load_contacts()
        if not contacts:
            print("Контакты техадминов не заданы.")
            return
        users_by_id = {user_id: (fullname, username) for user_id, fullname, username in get_all_users()}
        print("Техадмины:")
        for value in contacts:
            fullname, username = users_by_id.get(value, (f"Пользователь {value}", ""))
            print(f"- {fullname} ({_username_or_id(username, value)})")
        return

    if action == "contacts-add":
        init_db()
        users = get_all_users()
        existing = set(alerts_ops.load_contacts())
        candidates = [item for item in users if item[0] not in existing]
        if not candidates:
            print("Нет доступных пользователей для добавления.")
            return
        contact_id = _choose_user_from_directory("Выберите пользователя для добавления в техадмины:", candidates)
        if contact_id is None:
            return
        contacts = alerts_ops.add_contact(contact_id)
        print(colorize(f"Контакт добавлен. Всего: {len(contacts)}", "green"))
        return

    if action == "contacts-remove":
        init_db()
        contacts = alerts_ops.load_contacts()
        if not contacts:
            print("Техадмины не заданы.")
            return
        users_by_id = {user_id: (fullname, username) for user_id, fullname, username in get_all_users()}
        candidates: list[tuple[int, str, str]] = []
        for user_id in contacts:
            fullname, username = users_by_id.get(user_id, (f"Пользователь {user_id}", ""))
            candidates.append((user_id, fullname, username))
        contact_id = _choose_user_from_directory("Выберите техадмина для удаления:", candidates)
        if contact_id is None:
            return
        contacts = alerts_ops.remove_contact(contact_id)
        print(colorize(f"Контакт удален. Всего: {len(contacts)}", "green"))
        return

    if action == "alerts-test":
        message = _ask("Текст тестового уведомления (Enter = дефолт): ") or "Тестовое уведомление от menu."
        sent, failures = alerts_ops.send_alert(message)
        print(f"Отправлено: {sent}, ошибок: {len(failures)}")
        for chat_id, error in failures[:20]:
            print(f"- {chat_id}: {error}")
        return

    scope = "user"

    if action == "schedule-enable":
        interval = _ask_optional_int("Интервал, минут (Enter = 10): ") or 10
        service_path, timer_path = monitor_ops.install_monitor_timer(interval_min=interval, scope=scope)
        print(colorize(f"Monitor scheduler включен ({scope}).", "green"))
        print(f"Service: {service_path}")
        print(f"Timer: {timer_path}")
        return

    if action == "schedule-disable":
        monitor_ops.disable_monitor_timer(scope=scope)
        print(colorize(f"Monitor scheduler отключен ({scope}).", "green"))
        return

    if action == "schedule-status":
        monitor_ops.status_monitor_timer(scope=scope)
        return

    if action == "schedule-run":
        monitor_ops.run_monitor_now(scope=scope)
        print(colorize(f"Monitor job запущен ({scope}).", "green"))
        return

    units_csv = _ask(
        "Units CSV (например: bot,webapp). Enter = рекомендуемый набор для выбранного scope: "
    ) or None

    if action == "events-enable":
        template_path, dropins = monitor_ops.install_event_alerts(scope=scope, units_csv=units_csv)
        print(colorize(f"Событийные алерты включены ({scope}).", "green"))
        print(f"Template: {template_path}")
        print("Drop-ins:")
        for item in dropins:
            print(f"- {item}")
        return

    if action == "events-disable":
        removed = monitor_ops.disable_event_alerts(scope=scope, units_csv=units_csv)
        print(colorize(f"Событийные алерты отключены ({scope}).", "green"))
        print(f"Удалено drop-in: {len(removed)}")
        for item in removed:
            print(f"- {item}")
        return

    rows = monitor_ops.event_alerts_status(scope=scope, units_csv=units_csv)
    print(f"Статус событийных алертов ({scope}):")
    for unit_name, enabled, path in rows:
        state = colorize("ENABLED", "green") if enabled else colorize("DISABLED", "yellow")
        print(f"- {unit_name}: {state} ({path})")


def run_interactive_menu() -> int:
    while True:
        try:
            clear_terminal()
            print(colorize("Операционная CLI-панель", "cyan"))
            choice = _choose(
                "Главное меню:",
                [
                    ("status", "Статус компонентов"),
                    ("run", "Локальные компоненты (без systemd)"),
                    ("service", "Управление systemd-сервисами"),
                    ("broadcast", "Рассылка (wizard)"),
                    ("smoke", "Smoke-проверка WebApp"),
                    ("backup", "Backup БД"),
                    ("monitor", "Мониторинг и тех-уведомления"),
                    ("exit", "Выход"),
                ],
            )

            clear_terminal()
            if choice == "exit":
                print("Выход.")
                return 0
            if choice == "status":
                status_ops.print_status()
            elif choice == "run":
                _menu_run_component()
            elif choice == "service":
                _menu_service()
            elif choice == "broadcast":
                _menu_broadcast()
            elif choice == "smoke":
                url = _ask("Базовый URL (Enter = из WEBAPP_URL/localhost): ")
                smoke_ops.run_smoke(url or None)
            elif choice == "backup":
                _menu_backup()
            elif choice == "monitor":
                _menu_monitor()
            _pause()
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
            return 130
        except Exception as exc:
            print(colorize(f"Ошибка: {exc}", "red"))
            _pause()
