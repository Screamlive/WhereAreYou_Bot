import datetime
import logging
import sqlite3

from config import DB_NAME

VALID_SUPERADMIN_NOTIFY_MODES = {"global", "group_only", "selected_groups"}


def log_action(user_id: int, action: str) -> None:
    """
    Записываем действие в таблицу logs + выводим в консоль.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (action_time, user_id, action) VALUES (?, ?, ?)",
        (datetime.datetime.now().isoformat(), user_id, action)
    )
    conn.commit()
    conn.close()

    logging.info(f"[LOG_ACTION] user={user_id} | {action}")


def user_exists_in_db(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def is_user_approved(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return (row is not None) and (row[0] == 1)


def is_user_admin(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return (row is not None) and (row[0] == 1)


def get_admins() -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_admin=1")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_superadmin_notification_mode(user_id: int) -> str:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT mode
        FROM superadmin_notification_prefs
        WHERE user_id=?
        """,
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return "global"
    mode = row[0]
    return mode if mode in VALID_SUPERADMIN_NOTIFY_MODES else "global"


def get_superadmin_notification_groups(user_id: int) -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id
        FROM superadmin_notification_groups
        WHERE user_id=?
        ORDER BY group_id
        """,
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def set_superadmin_notification_mode(user_id: int, mode: str) -> bool:
    if mode not in VALID_SUPERADMIN_NOTIFY_MODES:
        return False

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO superadmin_notification_prefs (user_id, mode, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            mode=excluded.mode,
            updated_at=excluded.updated_at
        """,
        (user_id, mode, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True


def set_superadmin_notification_groups(user_id: int, group_ids: list[int]) -> None:
    unique_group_ids = sorted(set(group_ids))
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM superadmin_notification_groups WHERE user_id=?", (user_id,))
    for group_id in unique_group_ids:
        cur.execute(
            """
            INSERT INTO superadmin_notification_groups (user_id, group_id)
            VALUES (?, ?)
            """,
            (user_id, group_id)
        )
    conn.commit()
    conn.close()


def set_superadmin_notification_scope(user_id: int, group_id: int | None) -> None:
    if group_id is None:
        set_superadmin_notification_mode(user_id, "global")
        set_superadmin_notification_groups(user_id, [])
        return
    set_superadmin_notification_mode(user_id, "selected_groups")
    set_superadmin_notification_groups(user_id, [group_id])


def get_superadmin_group_notification_ids(user_id: int) -> list[int] | None:
    mode = get_superadmin_notification_mode(user_id)
    if mode == "global":
        return None
    if mode == "selected_groups":
        return get_superadmin_notification_groups(user_id)

    # mode == "group_only"
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id
        FROM group_memberships
        WHERE user_id=? AND role IN ('admin', 'viewer')
        ORDER BY group_id
        """,
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_superadmins_for_groups(group_ids: list[int]) -> list[int]:
    target_group_ids = set(group_ids)
    recipients: list[int] = []
    for admin_id in get_admins():
        allowed_group_ids = get_superadmin_group_notification_ids(admin_id)
        if allowed_group_ids is None:
            recipients.append(admin_id)
            continue
        if target_group_ids.intersection(allowed_group_ids):
            recipients.append(admin_id)
    return recipients


def get_admin_notification_recipients(group_ids: list[int]) -> list[int]:
    target_group_ids = set(group_ids)
    superadmin_recipients = set(get_superadmins_for_groups(group_ids))
    recipients = set(superadmin_recipients)

    for group_id in target_group_ids:
        for admin_id in get_group_admins(group_id):
            if is_user_admin(admin_id):
                # Для суперадмина приоритет у его notification scope,
                # даже если он одновременно админ этой группы.
                if admin_id in superadmin_recipients:
                    recipients.add(admin_id)
                continue
            recipients.add(admin_id)

    return sorted(recipients)


def get_last_group_id(tg_id: int) -> int | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT last_group_id FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def set_last_group_id(tg_id: int, group_id: int | None) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_group_id=? WHERE telegram_id=?", (group_id, tg_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def list_all_groups() -> list[tuple[int, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM groups ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_name(group_id: int) -> str | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM groups WHERE id=?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_user_groups(tg_id: int) -> list[tuple[int, str, str]]:
    """
    Возвращает список групп пользователя: (group_id, group_name, role).
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT gm.group_id, g.name, gm.role
        FROM group_memberships gm
        JOIN groups g ON g.id = gm.group_id
        WHERE gm.user_id=?
        ORDER BY g.name
        """,
        (tg_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def user_in_group(tg_id: int, group_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM group_memberships WHERE user_id=? AND group_id=?
        """,
        (tg_id, group_id)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def has_pending_group_request(tg_id: int, group_id: int, req_type: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM group_requests
        WHERE user_id=? AND group_id=? AND type=? AND status='pending'
        """,
        (tg_id, group_id, req_type)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def is_group_admin(tg_id: int, group_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM group_memberships
        WHERE user_id=? AND group_id=? AND role='admin'
        """,
        (tg_id, group_id)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def is_group_viewer(tg_id: int, group_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM group_memberships
        WHERE user_id=? AND group_id=? AND role='viewer'
        """,
        (tg_id, group_id)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_group_admins(group_id: int) -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id
        FROM group_memberships
        WHERE group_id=? AND role='admin'
        """,
        (group_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_approved_users() -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT telegram_id, fullname, username
        FROM users
        WHERE is_approved=1
        ORDER BY fullname
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_members(group_id: int) -> list[tuple[int, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.telegram_id, u.fullname, u.username, gm.role
        FROM group_memberships gm
        JOIN users u ON u.telegram_id = gm.user_id
        WHERE gm.group_id=?
        ORDER BY u.fullname
        """,
        (group_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_users() -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT telegram_id, fullname, username
        FROM users
        ORDER BY fullname
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_user_fullname(tg_id: int) -> str:
    """
    Возвращает fullname + (@username), либо "User <id>", если записи нет.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT fullname, username FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        fullname, username = row
        if username:
            return f"{fullname} (@{username})"
        return f"{fullname}"
    return f"User {tg_id}"


def create_group(name: str, created_by: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO groups (name, created_at, created_by)
            VALUES (?, ?, ?)
            """,
            (name, datetime.datetime.now().isoformat(), created_by)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_group(group_id: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM group_memberships WHERE group_id=?", (group_id,))
    cur.execute("DELETE FROM group_requests WHERE group_id=?", (group_id,))
    cur.execute("DELETE FROM group_role_requests WHERE group_id=?", (group_id,))
    cur.execute("DELETE FROM superadmin_notification_groups WHERE group_id=?", (group_id,))
    cur.execute("UPDATE users SET last_group_id=NULL WHERE last_group_id=?", (group_id,))
    cur.execute("DELETE FROM groups WHERE id=?", (group_id,))
    conn.commit()
    conn.close()


def get_group_membership_role(user_id: int, group_id: int) -> str | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT role
        FROM group_memberships
        WHERE user_id=? AND group_id=?
        """,
        (user_id, group_id)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def update_group_membership_role(user_id: int, group_id: int, role: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE group_memberships
        SET role=?
        WHERE user_id=? AND group_id=?
        """,
        (role, user_id, group_id)
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def add_group_membership(user_id: int, group_id: int, role: str, created_by: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO group_memberships (user_id, group_id, role, created_at, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, group_id, role, datetime.datetime.now().isoformat(), created_by)
    )
    conn.commit()
    conn.close()


def list_group_admin_users(group_id: int) -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.telegram_id, u.fullname, u.username
        FROM group_memberships gm
        JOIN users u ON u.telegram_id = gm.user_id
        WHERE gm.group_id=? AND gm.role='admin'
        ORDER BY u.fullname
        """,
        (group_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_group_viewer_users(group_id: int) -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.telegram_id, u.fullname, u.username
        FROM group_memberships gm
        JOIN users u ON u.telegram_id = gm.user_id
        WHERE gm.group_id=? AND gm.role='viewer'
        ORDER BY u.fullname
        """,
        (group_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def remove_user_from_group(user_id: int, group_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM group_memberships
        WHERE user_id=? AND group_id=?
        """,
        (user_id, group_id)
    )
    deleted = cur.rowcount > 0
    cur.execute(
        """
        UPDATE users
        SET last_group_id=NULL
        WHERE telegram_id=? AND last_group_id=?
        """,
        (user_id, group_id)
    )
    conn.commit()
    conn.close()
    return deleted


def list_pending_group_requests(req_type: str, group_id: int | None = None) -> list[tuple[int, int, str, str, int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if group_id:
        cur.execute(
            """
            SELECT gr.id, gr.user_id, u.fullname, u.username, g.id, g.name, gr.type
            FROM group_requests gr
            JOIN users u ON u.telegram_id = gr.user_id
            JOIN groups g ON g.id = gr.group_id
            WHERE gr.status='pending' AND gr.group_id=? AND gr.type=?
            ORDER BY u.fullname
            """,
            (group_id, req_type)
        )
    else:
        cur.execute(
            """
            SELECT gr.id, gr.user_id, u.fullname, u.username, g.id, g.name, gr.type
            FROM group_requests gr
            JOIN users u ON u.telegram_id = gr.user_id
            JOIN groups g ON g.id = gr.group_id
            WHERE gr.status='pending' AND gr.type=?
            ORDER BY g.name, u.fullname
            """,
            (req_type,)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_request(req_id: int) -> tuple[int, int, str, str] | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, group_id, type, status
        FROM group_requests
        WHERE id=?
        """,
        (req_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def set_group_request_status(req_id: int, status: str, reviewed_at: str, reviewed_by: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE group_requests
        SET status=?, reviewed_at=?, reviewed_by=?
        WHERE id=?
        """,
        (status, reviewed_at, reviewed_by, req_id)
    )
    conn.commit()
    conn.close()


def create_group_request(user_id: int, group_id: int, req_type: str, requested_by: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO group_requests (user_id, group_id, type, status, requested_at, requested_by)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (user_id, group_id, req_type, datetime.datetime.now().isoformat(), requested_by)
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return req_id


def has_pending_group_role_request(tg_id: int, group_id: int, target_role: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM group_role_requests
        WHERE user_id=? AND group_id=? AND target_role=? AND status='pending'
        """,
        (tg_id, group_id, target_role)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def create_group_role_request(user_id: int, group_id: int, target_role: str, requested_by: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO group_role_requests (user_id, group_id, target_role, status, requested_at, requested_by)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (user_id, group_id, target_role, datetime.datetime.now().isoformat(), requested_by)
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return req_id


def list_pending_group_role_requests(
    target_role: str,
    group_id: int | None = None
) -> list[tuple[int, int, str, str, int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if group_id:
        cur.execute(
            """
            SELECT grr.id, grr.user_id, u.fullname, u.username, g.id, g.name, grr.target_role
            FROM group_role_requests grr
            JOIN users u ON u.telegram_id = grr.user_id
            JOIN groups g ON g.id = grr.group_id
            WHERE grr.status='pending' AND grr.group_id=? AND grr.target_role=?
            ORDER BY u.fullname
            """,
            (group_id, target_role)
        )
    else:
        cur.execute(
            """
            SELECT grr.id, grr.user_id, u.fullname, u.username, g.id, g.name, grr.target_role
            FROM group_role_requests grr
            JOIN users u ON u.telegram_id = grr.user_id
            JOIN groups g ON g.id = grr.group_id
            WHERE grr.status='pending' AND grr.target_role=?
            ORDER BY g.name, u.fullname
            """,
            (target_role,)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_role_request(req_id: int) -> tuple[int, int, str, str] | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, group_id, target_role, status
        FROM group_role_requests
        WHERE id=?
        """,
        (req_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def set_group_role_request_status(req_id: int, status: str, reviewed_at: str, reviewed_by: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE group_role_requests
        SET status=?, reviewed_at=?, reviewed_by=?
        WHERE id=?
        """,
        (status, reviewed_at, reviewed_by, req_id)
    )
    conn.commit()
    conn.close()


def create_absence(
    user_id: int,
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
    status: str,
) -> int:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO absences (user_id, category, start_date, end_date, comment, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, category, start_date, end_date, comment, status)
    )
    abs_id = cur.lastrowid
    conn.commit()
    conn.close()
    return abs_id


def list_user_absences(user_id: int) -> list[tuple[int, str, str, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, category, start_date, end_date, comment, status
        FROM absences
        WHERE user_id=?
        ORDER BY start_date
        """,
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_absence_by_id(abs_id: int) -> tuple[int, str, str, str, str, str] | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, category, start_date, end_date, comment, status
        FROM absences
        WHERE id=?
        """,
        (abs_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def get_absence_with_user(abs_id: int) -> tuple[int, int, str, str, str, str, str, str, str] | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.id,
               a.user_id,
               a.category,
               a.start_date,
               a.end_date,
               a.comment,
               a.status,
               u.fullname,
               u.username
        FROM absences a
        JOIN users u ON u.telegram_id = a.user_id
        WHERE a.id=?
        """,
        (abs_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def get_user_group_ids(tg_id: int) -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id
        FROM group_memberships
        WHERE user_id=?
        ORDER BY group_id
        """,
        (tg_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def list_absences_for_period(
    start_date: str,
    end_date: str,
    statuses: list[str] | None = None,
    categories: list[str] | None = None,
    group_id: int | None = None,
    only_superadmins: bool = False,
    search_query: str | None = None,
) -> list[tuple[int, int, str, str, str, str, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    joins = ["JOIN users u ON u.telegram_id = a.user_id"]
    filters = [
        "date(a.start_date) <= date(?)",
        "date(a.end_date) >= date(?)",
    ]
    params: list[object] = [end_date, start_date]

    if group_id is not None:
        joins.append("JOIN group_memberships gm ON gm.user_id = a.user_id")
        filters.append("gm.group_id=?")
        params.append(group_id)

    if only_superadmins:
        filters.append("u.is_admin=1")

    normalized_statuses = sorted(set(s for s in (statuses or []) if s))
    if normalized_statuses:
        placeholders = ", ".join("?" for _ in normalized_statuses)
        filters.append(f"a.status IN ({placeholders})")
        params.extend(normalized_statuses)

    normalized_categories = sorted(set(c for c in (categories or []) if c))
    if normalized_categories:
        placeholders = ", ".join("?" for _ in normalized_categories)
        filters.append(f"a.category IN ({placeholders})")
        params.extend(normalized_categories)

    q = (search_query or "").strip().lower()
    if q:
        filters.append(
            "(lower(u.fullname) LIKE ? OR lower(COALESCE(u.username, '')) LIKE ?)"
        )
        pattern = f"%{q}%"
        params.extend([pattern, pattern])

    sql = f"""
        SELECT DISTINCT a.id,
               a.user_id,
               u.fullname,
               u.username,
               a.category,
               a.start_date,
               a.end_date,
               a.comment,
               a.status
        FROM absences a
        {" ".join(joins)}
        WHERE {" AND ".join(filters)}
        ORDER BY u.fullname, a.start_date, a.id
    """
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def update_absence(abs_id: int, category: str, start_date: str, end_date: str, comment: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE absences
        SET category=?, start_date=?, end_date=?, comment=?
        WHERE id=?
        """,
        (category, start_date, end_date, comment, abs_id)
    )
    conn.commit()
    conn.close()


def update_absence_status(abs_id: int, status: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE absences SET status=? WHERE id=?", (status, abs_id))
    conn.commit()
    conn.close()


def delete_absence(abs_id: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM absences WHERE id=?", (abs_id,))
    conn.commit()
    conn.close()


def list_pending_absences(group_id: int | None = None) -> list[tuple[int, int, str, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if group_id:
        cur.execute(
            """
            SELECT a.id, a.user_id, a.category, a.start_date, a.end_date, a.comment
            FROM absences a
            JOIN group_memberships gm ON gm.user_id = a.user_id
            WHERE a.status='pending' AND gm.group_id=?
            ORDER BY a.start_date
            """,
            (group_id,)
        )
    else:
        cur.execute(
            """
            SELECT a.id, a.user_id, a.category, a.start_date, a.end_date, a.comment
            FROM absences a
            WHERE a.status='pending'
            ORDER BY a.start_date
            """
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_overlapping_absences(
    start_date: str,
    end_date: str,
    exclude_user_id: int,
    group_id: int | None = None,
) -> list[tuple[int, int, str, str, str, str, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if group_id:
        cur.execute(
            """
            SELECT a.id,
                   a.user_id,
                   a.category,
                   a.start_date,
                   a.end_date,
                   a.comment,
                   a.status,
                   u.fullname,
                   u.username
            FROM absences a
            JOIN users u ON a.user_id = u.telegram_id
            JOIN group_memberships gm ON gm.user_id = a.user_id
            WHERE a.user_id != ?
              AND a.status != 'declined'
              AND gm.group_id = ?
              AND date(a.start_date) <= date(?)
              AND date(a.end_date) >= date(?)
            ORDER BY a.start_date
            """,
            (exclude_user_id, group_id, end_date, start_date)
        )
    else:
        cur.execute(
            """
            SELECT a.id,
                   a.user_id,
                   a.category,
                   a.start_date,
                   a.end_date,
                   a.comment,
                   a.status,
                   u.fullname,
                   u.username
            FROM absences a
            JOIN users u ON a.user_id = u.telegram_id
            WHERE a.user_id != ?
              AND a.status != 'declined'
              AND date(a.start_date) <= date(?)
              AND date(a.end_date) >= date(?)
            ORDER BY a.start_date
            """,
            (exclude_user_id, end_date, start_date)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def create_edit_request(
    abs_id: int,
    new_cat: str,
    new_sd: str,
    new_ed: str,
    new_comment: str,
    user_id: int,
) -> int:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO edit_requests (abs_id, new_cat, new_sd, new_ed, new_comment, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (abs_id, new_cat, new_sd, new_ed, new_comment, user_id)
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return req_id


def get_edit_request(req_id: int) -> tuple[int, str, str, str, str, int] | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT abs_id, new_cat, new_sd, new_ed, new_comment, user_id FROM edit_requests WHERE id=?",
        (req_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def delete_edit_request(req_id: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM edit_requests WHERE id=?", (req_id,))
    conn.commit()
    conn.close()


def list_approved_absences_between(
    start_date: str,
    end_date: str,
    group_id: int | None = None,
) -> list[tuple[int, str, str, str, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if group_id:
        cur.execute(
            """
            SELECT a.user_id, a.category, a.start_date, a.end_date, a.comment,
                   u.fullname, u.username
            FROM absences a
            JOIN users u ON a.user_id = u.telegram_id
            JOIN group_memberships gm ON gm.user_id = a.user_id
            WHERE a.status='approved'
              AND gm.group_id=?
              AND date(a.start_date) <= date(?)
              AND date(a.end_date) >= date(?)
            ORDER BY a.start_date
            """,
            (group_id, end_date, start_date)
        )
    else:
        cur.execute(
            """
            SELECT a.user_id, a.category, a.start_date, a.end_date, a.comment,
                   u.fullname, u.username
            FROM absences a
            JOIN users u ON a.user_id = u.telegram_id
            WHERE a.status='approved'
              AND date(a.start_date) <= date(?)
              AND date(a.end_date) >= date(?)
            ORDER BY a.start_date
            """,
            (end_date, start_date)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_approved_absences_for_date(
    date_iso: str,
    group_id: int | None = None,
) -> list[tuple[int, str, str, str, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if group_id:
        cur.execute(
            """
            SELECT a.user_id,
                   a.category,
                   a.start_date,
                   a.end_date,
                   a.comment,
                   u.fullname,
                   u.username
            FROM absences a
            JOIN users u ON a.user_id = u.telegram_id
            JOIN group_memberships gm ON gm.user_id = a.user_id
            WHERE a.status='approved'
              AND gm.group_id=?
              AND date(a.start_date) <= date(?)
              AND date(a.end_date) >= date(?)
            ORDER BY a.start_date
            """,
            (group_id, date_iso, date_iso)
        )
    else:
        cur.execute(
            """
            SELECT a.user_id,
                   a.category,
                   a.start_date,
                   a.end_date,
                   a.comment,
                   u.fullname,
                   u.username
            FROM absences a
            JOIN users u ON a.user_id = u.telegram_id
            WHERE a.status='approved'
              AND date(a.start_date) <= date(?)
              AND date(a.end_date) >= date(?)
            ORDER BY a.start_date
            """,
            (date_iso, date_iso)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def upsert_user_registration(tg_id: int, username: str, fullname: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE users
            SET username=?, fullname=?, is_approved=0
            WHERE telegram_id=?
            """,
            (username, fullname, tg_id)
        )
    else:
        cur.execute(
            """
            INSERT INTO users (telegram_id, username, fullname, is_approved, is_admin)
            VALUES (?, ?, ?, 0, 0)
            """,
            (tg_id, username, fullname)
        )
    conn.commit()
    conn.close()


def get_user_approval_status(tg_id: int) -> int | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def approve_user(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_approved=1 WHERE telegram_id=?", (tg_id,))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_user_and_related(tg_id: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM group_memberships WHERE user_id=?", (tg_id,))
    cur.execute("DELETE FROM group_requests WHERE user_id=?", (tg_id,))
    cur.execute("DELETE FROM group_role_requests WHERE user_id=?", (tg_id,))
    cur.execute("DELETE FROM superadmin_notification_groups WHERE user_id=?", (tg_id,))
    cur.execute("DELETE FROM superadmin_notification_prefs WHERE user_id=?", (tg_id,))
    cur.execute("DELETE FROM absences WHERE user_id=?", (tg_id,))
    cur.execute("DELETE FROM edit_requests WHERE user_id=?", (tg_id,))
    cur.execute("UPDATE users SET last_group_id=NULL WHERE telegram_id=?", (tg_id,))
    cur.execute("DELETE FROM users WHERE telegram_id=?", (tg_id,))
    conn.commit()
    conn.close()


def list_pending_user_ids() -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_approved=0")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def list_non_admin_approved_users() -> list[tuple[int, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT telegram_id, fullname
        FROM users
        WHERE is_approved=1
            AND is_admin=0
        ORDER BY fullname
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_admin_users(exclude_id: int | None = None) -> list[tuple[int, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if exclude_id is None:
        cur.execute(
            """
            SELECT telegram_id, fullname
            FROM users
            WHERE is_admin=1
            ORDER BY fullname
            """
        )
    else:
        cur.execute(
            """
            SELECT telegram_id, fullname
            FROM users
            WHERE is_admin=1
              AND telegram_id != ?
            ORDER BY fullname
            """,
            (exclude_id,)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def promote_to_admin(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_approved=1, is_admin=1 WHERE telegram_id=?", (tg_id,))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def revoke_admin(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin=0 WHERE telegram_id=?", (tg_id,))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def update_user_fullname(tg_id: int, fullname: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET fullname=? WHERE telegram_id=?", (fullname, tg_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def get_user_name_and_username(tg_id: int) -> tuple[str, str] | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT fullname, username FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row if row else None
