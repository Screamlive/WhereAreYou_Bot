"""User-related SQL access layer."""

import datetime
import sqlite3

from app.db import db_repo as _legacy_db_repo
from config import DB_NAME as _CONFIG_DB_NAME

VALID_SUPERADMIN_NOTIFY_MODES = {"global", "group_only", "selected_groups"}


def _connect() -> sqlite3.Connection:
    # Keep compatibility with tests overriding db_repo.DB_NAME at runtime.
    db_name = getattr(_legacy_db_repo, "DB_NAME", _CONFIG_DB_NAME)
    return sqlite3.connect(db_name)


def user_exists_in_db(tg_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def is_user_approved(tg_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return (row is not None) and (row[0] == 1)


def is_user_admin(tg_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return (row is not None) and (row[0] == 1)


def get_admins() -> list[int]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_admin=1")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_superadmin_notification_mode(user_id: int) -> str:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT mode
        FROM superadmin_notification_prefs
        WHERE user_id=?
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return "global"
    mode = row[0]
    return mode if mode in VALID_SUPERADMIN_NOTIFY_MODES else "global"


def get_superadmin_notification_groups(user_id: int) -> list[int]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id
        FROM superadmin_notification_groups
        WHERE user_id=?
        ORDER BY group_id
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def set_superadmin_notification_mode(user_id: int, mode: str) -> bool:
    if mode not in VALID_SUPERADMIN_NOTIFY_MODES:
        return False

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO superadmin_notification_prefs (user_id, mode, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            mode=excluded.mode,
            updated_at=excluded.updated_at
        """,
        (user_id, mode, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return True


def set_superadmin_notification_groups(user_id: int, group_ids: list[int]) -> None:
    unique_group_ids = sorted(set(group_ids))
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM superadmin_notification_groups WHERE user_id=?", (user_id,))
    for group_id in unique_group_ids:
        cur.execute(
            """
            INSERT INTO superadmin_notification_groups (user_id, group_id)
            VALUES (?, ?)
            """,
            (user_id, group_id),
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
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id
        FROM group_memberships
        WHERE user_id=? AND role IN ('admin', 'viewer')
        ORDER BY group_id
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_last_group_id(tg_id: int) -> int | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT last_group_id FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def set_last_group_id(tg_id: int, group_id: int | None) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_group_id=? WHERE telegram_id=?", (group_id, tg_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def get_user_groups(tg_id: int) -> list[tuple[int, str, str]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT gm.group_id, g.name, gm.role
        FROM group_memberships gm
        JOIN groups g ON g.id = gm.group_id
        WHERE gm.user_id=?
        ORDER BY g.name
        """,
        (tg_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_approved_users() -> list[tuple[int, str, str]]:
    conn = _connect()
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


def get_all_users() -> list[tuple[int, str, str]]:
    conn = _connect()
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
    conn = _connect()
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


def get_user_group_ids(tg_id: int) -> list[int]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id
        FROM group_memberships
        WHERE user_id=?
        ORDER BY group_id
        """,
        (tg_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def upsert_user_registration(tg_id: int, username: str, fullname: str) -> None:
    conn = _connect()
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
            (username, fullname, tg_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO users (telegram_id, username, fullname, is_approved, is_admin)
            VALUES (?, ?, ?, 0, 0)
            """,
            (tg_id, username, fullname),
        )
    conn.commit()
    conn.close()


def get_user_approval_status(tg_id: int) -> int | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def approve_user(tg_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_approved=1 WHERE telegram_id=?", (tg_id,))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_user_and_related(tg_id: int) -> None:
    conn = _connect()
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
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_approved=0")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def list_non_admin_approved_users() -> list[tuple[int, str]]:
    conn = _connect()
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
    conn = _connect()
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
            (exclude_id,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def promote_to_admin(tg_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_approved=1, is_admin=1 WHERE telegram_id=?", (tg_id,))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def revoke_admin(tg_id: int) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin=0 WHERE telegram_id=?", (tg_id,))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def update_user_fullname(tg_id: int, fullname: str) -> bool:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET fullname=? WHERE telegram_id=?", (fullname, tg_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def get_user_name_and_username(tg_id: int) -> tuple[str, str] | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT fullname, username FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row if row else None


__all__ = [
    "VALID_SUPERADMIN_NOTIFY_MODES",
    "approve_user",
    "delete_user_and_related",
    "get_admins",
    "get_all_users",
    "get_approved_users",
    "get_last_group_id",
    "get_superadmin_group_notification_ids",
    "get_superadmin_notification_groups",
    "get_superadmin_notification_mode",
    "get_user_approval_status",
    "get_user_fullname",
    "get_user_group_ids",
    "get_user_groups",
    "get_user_name_and_username",
    "is_user_admin",
    "is_user_approved",
    "list_admin_users",
    "list_non_admin_approved_users",
    "list_pending_user_ids",
    "promote_to_admin",
    "revoke_admin",
    "set_last_group_id",
    "set_superadmin_notification_groups",
    "set_superadmin_notification_mode",
    "set_superadmin_notification_scope",
    "update_user_fullname",
    "upsert_user_registration",
    "user_exists_in_db",
]
