"""Absence-related repository facade."""

from db_repo import (
    get_absence_with_user as _get_absence_with_user,
    list_absences_for_period as _list_absences_for_period,
    list_pending_absences as _list_pending_absences,
)


def list_pending_absences(group_id: int | None = None) -> list[tuple]:
    return _list_pending_absences(group_id)


def list_absences_for_period(
    start_date: str,
    end_date: str,
    statuses: list[str] | None = None,
    categories: list[str] | None = None,
    group_id: int | None = None,
    only_superadmins: bool = False,
    search_query: str | None = None,
) -> list[tuple]:
    return _list_absences_for_period(
        start_date=start_date,
        end_date=end_date,
        statuses=statuses,
        categories=categories,
        group_id=group_id,
        only_superadmins=only_superadmins,
        search_query=search_query,
    )


def get_absence_with_user(absence_id: int) -> tuple[int, int, str, str, str, str, str, str, str] | None:
    return _get_absence_with_user(absence_id)
