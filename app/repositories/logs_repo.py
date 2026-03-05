"""Logging-related repository facade."""

from app.db.logs import log_action as _log_action


def log_action(user_id: int, action: str) -> None:
    _log_action(user_id, action)
