"""Logging-related database functions.

Current implementation is delegated to the legacy monolith module.
"""

from app.db.db_repo import log_action

__all__ = ["log_action"]
