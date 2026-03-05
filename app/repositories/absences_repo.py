"""Absence-related repository facade."""

from app.db.absences import (
    create_absence as _create_absence,
    create_edit_request as _create_edit_request,
    delete_absence as _delete_absence,
    delete_edit_request as _delete_edit_request,
    get_absence_by_id as _get_absence_by_id,
    get_edit_request as _get_edit_request,
    get_absence_with_user as _get_absence_with_user,
    list_approved_absences_between as _list_approved_absences_between,
    list_approved_absences_for_date as _list_approved_absences_for_date,
    list_absences_for_period as _list_absences_for_period,
    list_overlapping_absences as _list_overlapping_absences,
    list_pending_absences as _list_pending_absences,
    list_user_absences as _list_user_absences,
    update_absence as _update_absence,
    update_absence_status as _update_absence_status,
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


def create_absence(
    user_id: int,
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
    status: str,
) -> int:
    return _create_absence(user_id, category, start_date, end_date, comment, status)


def list_user_absences(user_id: int) -> list[tuple[int, str, str, str, str, str]]:
    return _list_user_absences(user_id)


def get_absence_by_id(absence_id: int) -> tuple[int, str, str, str, str, str] | None:
    return _get_absence_by_id(absence_id)


def update_absence(absence_id: int, category: str, start_date: str, end_date: str, comment: str) -> None:
    _update_absence(absence_id, category, start_date, end_date, comment)


def update_absence_status(absence_id: int, status: str) -> None:
    _update_absence_status(absence_id, status)


def delete_absence(absence_id: int) -> None:
    _delete_absence(absence_id)


def list_overlapping_absences(
    start_date: str,
    end_date: str,
    exclude_user_id: int,
    group_id: int | None = None,
) -> list[tuple]:
    return _list_overlapping_absences(start_date, end_date, exclude_user_id, group_id=group_id)


def create_edit_request(
    absence_id: int,
    new_category: str,
    new_start: str,
    new_end: str,
    new_comment: str,
    requested_by: int,
) -> int:
    return _create_edit_request(
        absence_id,
        new_category,
        new_start,
        new_end,
        new_comment,
        requested_by,
    )


def get_edit_request(request_id: int) -> tuple[int, str, str, str, str, int] | None:
    return _get_edit_request(request_id)


def delete_edit_request(request_id: int) -> None:
    _delete_edit_request(request_id)


def list_approved_absences_between(
    start_date: str,
    end_date: str,
    group_id: int | None = None,
) -> list[tuple]:
    return _list_approved_absences_between(start_date, end_date, group_id)


def list_approved_absences_for_date(date_iso: str, group_id: int | None = None) -> list[tuple]:
    return _list_approved_absences_for_date(date_iso, group_id)
