"""Repository facades used by application services."""

from app.repositories.absences_repo import list_pending_absences
from app.repositories.groups_repo import (
    get_group_admins,
    get_group_members,
    get_group_name,
    list_all_groups,
    list_pending_group_requests,
)
from app.repositories.users_repo import (
    get_admins,
    get_all_users,
    get_approved_users,
    get_superadmin_group_notification_ids,
    get_superadmin_notification_mode,
    get_user_fullname,
    list_pending_user_ids,
)

__all__ = [
    "get_admins",
    "get_all_users",
    "get_approved_users",
    "get_group_admins",
    "get_group_members",
    "get_group_name",
    "get_superadmin_group_notification_ids",
    "get_superadmin_notification_mode",
    "get_user_fullname",
    "list_all_groups",
    "list_pending_absences",
    "list_pending_group_requests",
    "list_pending_user_ids",
]
