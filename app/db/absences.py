"""Absence-related SQL access layer."""

import sqlite3

from app.db import db_repo as _legacy_db_repo
from config import DB_NAME as _CONFIG_DB_NAME


def _connect() -> sqlite3.Connection:
    # Keep compatibility with tests overriding db_repo.DB_NAME at runtime.
    db_name = getattr(_legacy_db_repo, "DB_NAME", _CONFIG_DB_NAME)
    return sqlite3.connect(db_name)


def create_absence(
    user_id: int,
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
    status: str,
) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO absences (user_id, category, start_date, end_date, comment, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, category, start_date, end_date, comment, status),
    )
    abs_id = cur.lastrowid
    conn.commit()
    conn.close()
    return abs_id


def list_user_absences(user_id: int) -> list[tuple[int, str, str, str, str, str]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, category, start_date, end_date, comment, status
        FROM absences
        WHERE user_id=?
        ORDER BY start_date
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_absence_by_id(abs_id: int) -> tuple[int, str, str, str, str, str] | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, category, start_date, end_date, comment, status
        FROM absences
        WHERE id=?
        """,
        (abs_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def get_absence_with_user(abs_id: int) -> tuple[int, int, str, str, str, str, str, str, str] | None:
    conn = _connect()
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
        (abs_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def list_absences_for_period(
    start_date: str,
    end_date: str,
    statuses: list[str] | None = None,
    categories: list[str] | None = None,
    group_id: int | None = None,
    only_superadmins: bool = False,
    search_query: str | None = None,
) -> list[tuple[int, int, str, str, str, str, str, str, str]]:
    conn = _connect()
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

    q = (search_query or "").strip()

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

    if q:
        q_casefold = q.casefold()

        def _matches_search(row: tuple[int, int, str, str, str, str, str, str, str]) -> bool:
            fullname = (row[2] or "").casefold()
            username = (row[3] or "").casefold()
            return (
                q_casefold in fullname
                or q_casefold in username
                or q_casefold in f"@{username}"
            )

        rows = [row for row in rows if _matches_search(row)]

    return rows


def update_absence(abs_id: int, category: str, start_date: str, end_date: str, comment: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE absences
        SET category=?, start_date=?, end_date=?, comment=?
        WHERE id=?
        """,
        (category, start_date, end_date, comment, abs_id),
    )
    conn.commit()
    conn.close()


def update_absence_status(abs_id: int, status: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE absences SET status=? WHERE id=?", (status, abs_id))
    conn.commit()
    conn.close()


def delete_absence(abs_id: int) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM absences WHERE id=?", (abs_id,))
    conn.commit()
    conn.close()


def list_pending_absences(group_id: int | None = None) -> list[tuple[int, int, str, str, str, str]]:
    conn = _connect()
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
            (group_id,),
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
    conn = _connect()
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
            (exclude_user_id, group_id, end_date, start_date),
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
            (exclude_user_id, end_date, start_date),
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
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO edit_requests (abs_id, new_cat, new_sd, new_ed, new_comment, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (abs_id, new_cat, new_sd, new_ed, new_comment, user_id),
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return req_id


def get_edit_request(req_id: int) -> tuple[int, str, str, str, str, int] | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT abs_id, new_cat, new_sd, new_ed, new_comment, user_id FROM edit_requests WHERE id=?",
        (req_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row if row else None


def delete_edit_request(req_id: int) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM edit_requests WHERE id=?", (req_id,))
    conn.commit()
    conn.close()


def list_approved_absences_between(
    start_date: str,
    end_date: str,
    group_id: int | None = None,
) -> list[tuple[int, str, str, str, str, str, str]]:
    conn = _connect()
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
            (group_id, end_date, start_date),
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
            (end_date, start_date),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_approved_absences_for_date(
    date_iso: str,
    group_id: int | None = None,
) -> list[tuple[int, str, str, str, str, str, str]]:
    conn = _connect()
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
            (group_id, date_iso, date_iso),
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
            (date_iso, date_iso),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


__all__ = [
    "create_absence",
    "create_edit_request",
    "delete_absence",
    "delete_edit_request",
    "get_absence_by_id",
    "get_absence_with_user",
    "get_edit_request",
    "list_absences_for_period",
    "list_approved_absences_between",
    "list_approved_absences_for_date",
    "list_overlapping_absences",
    "list_pending_absences",
    "list_user_absences",
    "update_absence",
    "update_absence_status",
]
