import datetime
import logging
import sqlite3

from config import DB_NAME


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
