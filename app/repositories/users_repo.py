"""User-related repository facade."""

from db_repo import (
    get_last_group_id as _get_last_group_id,
    get_admins as _get_admins,
    get_all_users as _get_all_users,
    get_approved_users as _get_approved_users,
    get_superadmin_group_notification_ids as _get_superadmin_group_notification_ids,
    get_superadmin_notification_mode as _get_superadmin_notification_mode,
    get_user_group_ids as _get_user_group_ids,
    get_user_groups as _get_user_groups,
    get_user_name_and_username as _get_user_name_and_username,
    get_user_fullname as _get_user_fullname,
    is_user_admin as _is_user_admin,
    is_user_approved as _is_user_approved,
    set_last_group_id as _set_last_group_id,
    user_exists_in_db as _user_exists_in_db,
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


def user_exists_in_db(user_id: int) -> bool:
    return _user_exists_in_db(user_id)


def is_user_approved(user_id: int) -> bool:
    return _is_user_approved(user_id)


def is_user_admin(user_id: int) -> bool:
    return _is_user_admin(user_id)


def get_user_name_and_username(user_id: int) -> tuple[str, str] | None:
    return _get_user_name_and_username(user_id)


def get_user_groups(user_id: int) -> list[tuple[int, str, str]]:
    return _get_user_groups(user_id)


def get_user_group_ids(user_id: int) -> list[int]:
    return _get_user_group_ids(user_id)


def get_last_group_id(user_id: int) -> int | None:
    return _get_last_group_id(user_id)


def set_last_group_id(user_id: int, group_id: int | None) -> bool:
    return _set_last_group_id(user_id, group_id)
