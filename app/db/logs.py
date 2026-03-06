"""Logging-related SQL access layer."""

import datetime
import logging
import sqlite3

from app.db import db_repo as _legacy_db_repo
from config import DB_NAME as _CONFIG_DB_NAME


def _connect() -> sqlite3.Connection:
    # Keep compatibility with tests overriding db_repo.DB_NAME at runtime.
    db_name = getattr(_legacy_db_repo, "DB_NAME", _CONFIG_DB_NAME)
    return sqlite3.connect(db_name)


def log_action(user_id: int, action: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (action_time, user_id, action) VALUES (?, ?, ?)",
        (datetime.datetime.now().isoformat(), user_id, action),
    )
    conn.commit()
    conn.close()

    logging.info(f"[LOG_ACTION] user={user_id} | {action}")


__all__ = ["log_action"]
