from collections import defaultdict

from aiogram import Bot

from app.repositories.absences_repo import list_pending_absences
from app.repositories.groups_repo import (
    get_group_admins,
    get_group_name,
    list_all_groups,
    list_pending_group_requests,
)
from app.repositories.users_repo import (
    get_admins,
    get_superadmin_group_notification_ids,
    get_superadmin_notification_mode,
    get_user_fullname,
    list_pending_user_ids,
)
from database import init_db
from settings import TOKEN


def build_group_admin_notifications() -> dict[int, str]:
    groups = list_all_groups()
    per_admin_sections: dict[int, list[str]] = defaultdict(list)

    for group_id, group_name in groups:
        pending_joins = list_pending_group_requests("join", group_id)
        pending_absences = list_pending_absences(group_id)

        if not pending_joins and not pending_absences:
            continue

        lines = [f"Группа «{group_name}»:"]
        if pending_joins:
            lines.append(f"- заявки на вступление: {len(pending_joins)}")
        if pending_absences:
            lines.append(f"- заявки на отсутствие: {len(pending_absences)}")

        section = "\n".join(lines)
        for admin_id in get_group_admins(group_id):
            per_admin_sections[admin_id].append(section)

    notifications: dict[int, str] = {}
    for admin_id, sections in per_admin_sections.items():
        text = "Ежедневная сводка по вашим группам:\n\n" + "\n\n".join(sections)
        notifications[admin_id] = text

    return notifications


def build_superadmin_notifications() -> dict[int, str]:
    pending_users = list_pending_user_ids()
    notifications: dict[int, str] = {}

    for admin_id in get_admins():
        mode = get_superadmin_notification_mode(admin_id)
        scope_group_ids = get_superadmin_group_notification_ids(admin_id)

        group_sections: list[str] = []
        if scope_group_ids is None:
            groups = list_all_groups()
        else:
            groups = [(gid, get_group_name(gid) or f"ID={gid}") for gid in scope_group_ids]

        for group_id, group_name in groups:
            pending_joins = list_pending_group_requests("join", group_id)
            pending_absences = list_pending_absences(group_id)
            if not pending_joins and not pending_absences:
                continue
            lines = [f"Группа «{group_name}»:"]
            if pending_joins:
                lines.append(f"- заявки на вступление: {len(pending_joins)}")
            if pending_absences:
                lines.append(f"- заявки на отсутствие: {len(pending_absences)}")
            group_sections.append("\n".join(lines))

        if not pending_users and not group_sections:
            continue

        parts = [f"Ежедневная сводка суперадмина (режим: {mode}):"]
        if pending_users:
            lines = [f"- {get_user_fullname(uid)} (ID={uid})" for uid in pending_users]
            parts.append(
                f"Новых заявок на регистрацию: {len(pending_users)}\n\n"
                "Список:\n" + "\n".join(lines)
            )
        if group_sections:
            parts.append("Групповые заявки:\n\n" + "\n\n".join(group_sections))

        notifications[admin_id] = "\n\n".join(parts)

    return notifications


async def send_daily_notifications() -> None:
    init_db()
    bot = Bot(token=TOKEN)

    try:
        group_admin_msgs = build_group_admin_notifications()
        superadmin_msgs = build_superadmin_notifications()

        for admin_id, text in group_admin_msgs.items():
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                pass

        for admin_id, text in superadmin_msgs.items():
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                pass
    finally:
        await bot.session.close()


def main() -> None:
    # Thin wrapper for backward compatibility with "python notifications.py".
    from app.entrypoints.notifications_main import main as run_main

    run_main()


if __name__ == "__main__":
    main()
