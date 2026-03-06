"""Group-related SQL access layer."""

import datetime
import sqlite3

from app.db import db_repo as _legacy_db_repo
from app.db.users import get_admins, get_superadmin_group_notification_ids, is_user_admin
from config import DB_NAME as _CONFIG_DB_NAME


def _connect() -> sqlite3.Connection:
    # Keep compatibility with tests overriding db_repo.DB_NAME at runtime.
    db_name = getattr(_legacy_db_repo, "DB_NAME", _CONFIG_DB_NAME)
    return sqlite3.connect(db_name)


def list_all_groups() -> list[tuple[int, str]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM groups ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_name(group_id: int) -> str | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM groups WHERE id=?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def user_in_group(tg_id: int, group_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM group_memberships WHERE user_id=? AND group_id=?
        """,
        (tg_id, group_id),
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def has_pending_group_request(tg_id: int, group_id: int, req_type: str) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM group_requests
        WHERE user_id=? AND group_id=? AND type=? AND status='pending'
        """,
        (tg_id, group_id, req_type),
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def is_group_admin(tg_id: int, group_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM group_memberships
        WHERE user_id=? AND group_id=? AND role='admin'
        """,
        (tg_id, group_id),
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_group_admins(group_id: int) -> list[int]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id
        FROM group_memberships
        WHERE group_id=? AND role='admin'
        """,
        (group_id,),
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
                # For superadmins, notification scope has priority even if
                # they are also admins of a specific group.
                if admin_id in superadmin_recipients:
                    recipients.add(admin_id)
                continue
            recipients.add(admin_id)

    return sorted(recipients)


def get_group_members(group_id: int) -> list[tuple[int, str, str, str]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.telegram_id, u.fullname, u.username, gm.role
        FROM group_memberships gm
        JOIN users u ON u.telegram_id = gm.user_id
        WHERE gm.group_id=?
        ORDER BY u.fullname
        """,
        (group_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def create_group(name: str, created_by: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO groups (name, created_at, created_by)
            VALUES (?, ?, ?)
            """,
            (name, datetime.datetime.now().isoformat(), created_by),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_group(group_id: int) -> None:
    conn = _connect()
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
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT role
        FROM group_memberships
        WHERE user_id=? AND group_id=?
        """,
        (user_id, group_id),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def update_group_membership_role(user_id: int, group_id: int, role: str) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE group_memberships
        SET role=?
        WHERE user_id=? AND group_id=?
        """,
        (role, user_id, group_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def add_group_membership(user_id: int, group_id: int, role: str, created_by: int) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO group_memberships (user_id, group_id, role, created_at, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, group_id, role, datetime.datetime.now().isoformat(), created_by),
    )
    conn.commit()
    conn.close()


def list_group_admin_users(group_id: int) -> list[tuple[int, str, str]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.telegram_id, u.fullname, u.username
        FROM group_memberships gm
        JOIN users u ON u.telegram_id = gm.user_id
        WHERE gm.group_id=? AND gm.role='admin'
        ORDER BY u.fullname
        """,
        (group_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_group_viewer_users(group_id: int) -> list[tuple[int, str, str]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.telegram_id, u.fullname, u.username
        FROM group_memberships gm
        JOIN users u ON u.telegram_id = gm.user_id
        WHERE gm.group_id=? AND gm.role='viewer'
        ORDER BY u.fullname
        """,
        (group_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def remove_user_from_group(user_id: int, group_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM group_memberships
        WHERE user_id=? AND group_id=?
        """,
        (user_id, group_id),
    )
    deleted = cur.rowcount > 0
    cur.execute(
        """
        UPDATE users
        SET last_group_id=NULL
        WHERE telegram_id=? AND last_group_id=?
        """,
        (user_id, group_id),
    )
    conn.commit()
    conn.close()
    return deleted


def list_pending_group_requests(req_type: str, group_id: int | None = None) -> list[tuple[int, int, str, str, int, str, str]]:
    conn = _connect()
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
            (group_id, req_type),
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
            (req_type,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_request(req_id: int) -> tuple[int, int, str, str] | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, group_id, type, status
        FROM group_requests
        WHERE id=?
        """,
        (req_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def set_group_request_status(req_id: int, status: str, reviewed_at: str, reviewed_by: int) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE group_requests
        SET status=?, reviewed_at=?, reviewed_by=?
        WHERE id=?
        """,
        (status, reviewed_at, reviewed_by, req_id),
    )
    conn.commit()
    conn.close()


def create_group_request(user_id: int, group_id: int, req_type: str, requested_by: int) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO group_requests (user_id, group_id, type, status, requested_at, requested_by)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (user_id, group_id, req_type, datetime.datetime.now().isoformat(), requested_by),
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return req_id


def has_pending_group_role_request(tg_id: int, group_id: int, target_role: str) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM group_role_requests
        WHERE user_id=? AND group_id=? AND target_role=? AND status='pending'
        """,
        (tg_id, group_id, target_role),
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def create_group_role_request(user_id: int, group_id: int, target_role: str, requested_by: int) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO group_role_requests (user_id, group_id, target_role, status, requested_at, requested_by)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (user_id, group_id, target_role, datetime.datetime.now().isoformat(), requested_by),
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return req_id


def list_pending_group_role_requests(
    target_role: str,
    group_id: int | None = None,
) -> list[tuple[int, int, str, str, int, str, str]]:
    conn = _connect()
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
            (group_id, target_role),
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
            (target_role,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_role_request(req_id: int) -> tuple[int, int, str, str] | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, group_id, target_role, status
        FROM group_role_requests
        WHERE id=?
        """,
        (req_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def set_group_role_request_status(req_id: int, status: str, reviewed_at: str, reviewed_by: int) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE group_role_requests
        SET status=?, reviewed_at=?, reviewed_by=?
        WHERE id=?
        """,
        (status, reviewed_at, reviewed_by, req_id),
    )
    conn.commit()
    conn.close()


__all__ = [
    "add_group_membership",
    "create_group",
    "create_group_request",
    "create_group_role_request",
    "delete_group",
    "get_admin_notification_recipients",
    "get_group_admins",
    "get_group_members",
    "get_group_membership_role",
    "get_group_name",
    "get_group_request",
    "get_group_role_request",
    "get_superadmins_for_groups",
    "has_pending_group_request",
    "has_pending_group_role_request",
    "is_group_admin",
    "list_all_groups",
    "list_group_admin_users",
    "list_group_viewer_users",
    "list_pending_group_requests",
    "list_pending_group_role_requests",
    "remove_user_from_group",
    "set_group_request_status",
    "set_group_role_request_status",
    "update_group_membership_role",
    "user_in_group",
]
