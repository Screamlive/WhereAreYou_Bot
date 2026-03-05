"""User-related repository facade."""

from db_repo import (
    get_admins as _get_admins,
    get_all_users as _get_all_users,
    get_approved_users as _get_approved_users,
    get_superadmin_group_notification_ids as _get_superadmin_group_notification_ids,
    get_superadmin_notification_mode as _get_superadmin_notification_mode,
    get_user_fullname as _get_user_fullname,
    list_pending_user_ids as _list_pending_user_ids,
)


def get_admins() -> list[int]:
    return _get_admins()


def get_all_users() -> list[tuple[int, str, str]]:
    return _get_all_users()


def get_approved_users() -> list[tuple[int, str, str]]:
    return _get_approved_users()


def list_pending_user_ids() -> list[int]:
    return _list_pending_user_ids()


def get_user_fullname(user_id: int) -> str:
    return _get_user_fullname(user_id)


def get_superadmin_notification_mode(user_id: int) -> str:
    return _get_superadmin_notification_mode(user_id)


def get_superadmin_group_notification_ids(user_id: int) -> list[int] | None:
    return _get_superadmin_group_notification_ids(user_id)
