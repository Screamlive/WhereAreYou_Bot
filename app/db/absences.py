"""Absence-related database functions.

Current implementation is delegated to the legacy monolith module.
"""

from app.db.db_repo import (
    create_absence,
    create_edit_request,
    delete_absence,
    delete_edit_request,
    get_absence_by_id,
    get_absence_with_user,
    get_edit_request,
    list_absences_for_period,
    list_approved_absences_between,
    list_approved_absences_for_date,
    list_overlapping_absences,
    list_pending_absences,
    list_user_absences,
    update_absence,
    update_absence_status,
)

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
