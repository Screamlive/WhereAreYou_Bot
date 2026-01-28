#!/usr/bin/env python3
"""
Minimal smoke check for database.init_db().
Creates a temporary SQLite DB and verifies required tables exist.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database


def main() -> int:
    fd, path = tempfile.mkstemp(prefix="bot_db_smoke_", suffix=".db")
    os.close(fd)

    database.DB_NAME = path
    database.init_db()

    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()

    tables = {r[0] for r in rows} - {"sqlite_sequence"}
    expected = {
        "users",
        "absences",
        "logs",
        "edit_requests",
        "groups",
        "group_memberships",
        "group_requests",
    }
    missing = expected - tables

    if missing:
        print("Missing tables:", ", ".join(sorted(missing)))
        return 1

    print("OK: tables present:", ", ".join(sorted(expected)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
