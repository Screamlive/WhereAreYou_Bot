"""Use-cases for overlap calculation and admin recipient selection."""

from core import get_admin_groups, is_superadmin
from app.repositories.absences_repo import list_overlapping_absences
from app.repositories.groups_repo import get_admin_notification_recipients
from app.repositories.users_repo import get_superadmin_group_notification_ids, get_user_groups
from utils import format_date_display

OVERLAP_ITEMS_LIMIT = 10


def format_overlap_rows(
    rows: list[tuple],
    limit: int | None = OVERLAP_ITEMS_LIMIT,
    add_tail: bool = True,
) -> list[str]:
    if limit is None:
        visible_rows = rows
    else:
        visible_rows = rows[:limit]

    lines: list[str] = []
    for row in visible_rows:
        (_abs_id, _uid, category, sd, ed, _comment, status, fullname, username) = row
        name = f"{fullname} (@{username})" if username else fullname
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        lines.append(f"{name} — {category} {sd_disp}–{ed_disp} ({status})")
    remaining = len(rows) - len(visible_rows)
    if add_tail and remaining > 0:
        lines.append(f"…и ещё {remaining}")
    return lines


def build_group_overlap_sections(
    group_rows: list[tuple[str, list[tuple]]],
    limit: int | None = OVERLAP_ITEMS_LIMIT,
    add_tail: bool = True,
) -> str | None:
    sections: list[str] = []
    for group_name, rows in group_rows:
        if not rows:
            continue
        lines = format_overlap_rows(rows, limit=limit, add_tail=add_tail)
        sections.append(f"Группа «{group_name}»:\n" + "\n".join(lines))
    if not sections:
        return None
    return "\n\n".join(sections)


def collect_overlaps_for_user_groups(
    target_user_id: int,
    start_date: str,
    end_date: str,
    full: bool = False,
) -> str | None:
    limit = None if full else OVERLAP_ITEMS_LIMIT
    group_rows: list[tuple[str, list[tuple]]] = []
    for gid, gname, _role in get_user_groups(target_user_id):
        rows = list_overlapping_absences(start_date, end_date, target_user_id, group_id=gid)
        group_rows.append((gname, rows))
    return build_group_overlap_sections(group_rows, limit=limit, add_tail=not full)


def collect_overlaps_for_superadmin_scope(
    superadmin_id: int,
    target_user_id: int,
    start_date: str,
    end_date: str,
    full: bool = False,
) -> str | None:
    limit = None if full else OVERLAP_ITEMS_LIMIT
    scope_group_ids = get_superadmin_group_notification_ids(superadmin_id)

    if scope_group_ids is None:
        rows = list_overlapping_absences(start_date, end_date, target_user_id, group_id=None)
        if not rows:
            return None
        lines = format_overlap_rows(rows, limit=limit, add_tail=not full)
        return "Пересечения по всем пользователям:\n" + "\n".join(lines)

    if not scope_group_ids:
        return None

    target_group_names = {gid: name for gid, name, _role in get_user_groups(target_user_id)}
    group_rows: list[tuple[str, list[tuple]]] = []
    for gid in scope_group_ids:
        if gid not in target_group_names:
            continue
        rows = list_overlapping_absences(start_date, end_date, target_user_id, group_id=gid)
        group_rows.append((target_group_names[gid], rows))

    sections = build_group_overlap_sections(group_rows, limit=limit, add_tail=not full)
    if not sections:
        return None
    return "Пересечения по фильтру суперадмина:\n\n" + sections


def collect_overlaps_for_requester(
    requester_id: int,
    target_user_id: int,
    start_date: str,
    end_date: str,
    full: bool = False,
) -> str | None:
    if is_superadmin(requester_id):
        return collect_overlaps_for_superadmin_scope(
            requester_id,
            target_user_id,
            start_date,
            end_date,
            full=full,
        )
    return collect_overlaps_for_user_groups(target_user_id, start_date, end_date, full=full)


def collect_overlaps_for_admin(
    admin_id: int,
    target_user_id: int,
    start_date: str,
    end_date: str,
    full: bool = False,
) -> str | None:
    if is_superadmin(admin_id):
        return collect_overlaps_for_superadmin_scope(
            admin_id,
            target_user_id,
            start_date,
            end_date,
            full=full,
        )

    limit = None if full else OVERLAP_ITEMS_LIMIT
    admin_groups = get_admin_groups(admin_id)
    if not admin_groups:
        return None

    target_group_names = {gid: name for gid, name, _role in get_user_groups(target_user_id)}
    group_rows: list[tuple[str, list[tuple]]] = []
    for gid, gname in admin_groups:
        if gid not in target_group_names:
            continue
        rows = list_overlapping_absences(start_date, end_date, target_user_id, group_id=gid)
        group_rows.append((gname, rows))
    sections = build_group_overlap_sections(group_rows, limit=limit, add_tail=not full)
    if not sections:
        return None
    return "Пересечения по группе:\n\n" + sections


def get_absence_recipients(target_user_id: int) -> set[int]:
    group_ids = [gid for gid, _name, _role in get_user_groups(target_user_id)]
    return set(get_admin_notification_recipients(group_ids))
