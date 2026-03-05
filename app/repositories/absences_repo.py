"""Absence-related repository facade."""

from db_repo import list_pending_absences as _list_pending_absences


def list_pending_absences(group_id: int | None = None) -> list[tuple]:
    return _list_pending_absences(group_id)
