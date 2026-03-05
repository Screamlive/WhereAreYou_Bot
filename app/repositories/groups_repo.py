"""Group-related repository facade."""

from app.db.db_repo import (
    add_group_membership as _add_group_membership,
    create_group as _create_group,
    create_group_request as _create_group_request,
    create_group_role_request as _create_group_role_request,
    delete_group as _delete_group,
    get_group_admins as _get_group_admins,
    get_group_request as _get_group_request,
    get_group_role_request as _get_group_role_request,
    get_admin_notification_recipients as _get_admin_notification_recipients,
    has_pending_group_request as _has_pending_group_request,
    has_pending_group_role_request as _has_pending_group_role_request,
    is_group_admin as _is_group_admin,
    get_group_membership_role as _get_group_membership_role,
    get_group_members as _get_group_members,
    get_group_name as _get_group_name,
    list_all_groups as _list_all_groups,
    list_group_admin_users as _list_group_admin_users,
    list_group_viewer_users as _list_group_viewer_users,
    list_pending_group_requests as _list_pending_group_requests,
    list_pending_group_role_requests as _list_pending_group_role_requests,
    remove_user_from_group as _remove_user_from_group,
    set_group_request_status as _set_group_request_status,
    set_group_role_request_status as _set_group_role_request_status,
    update_group_membership_role as _update_group_membership_role,
    user_in_group as _user_in_group,
)


def list_all_groups() -> list[tuple[int, str]]:
    return _list_all_groups()


def get_group_name(group_id: int) -> str | None:
    return _get_group_name(group_id)


def get_group_admins(group_id: int) -> list[int]:
    return _get_group_admins(group_id)


def get_group_members(group_id: int) -> list[tuple[int, str, str, str]]:
    return _get_group_members(group_id)


def get_group_membership_role(user_id: int, group_id: int) -> str | None:
    return _get_group_membership_role(user_id, group_id)


def get_admin_notification_recipients(group_ids: list[int]) -> list[int]:
    return _get_admin_notification_recipients(group_ids)


def user_in_group(user_id: int, group_id: int) -> bool:
    return _user_in_group(user_id, group_id)


def has_pending_group_request(user_id: int, group_id: int, request_type: str) -> bool:
    return _has_pending_group_request(user_id, group_id, request_type)


def create_group(name: str, created_by: int) -> bool:
    return _create_group(name, created_by)


def delete_group(group_id: int) -> None:
    _delete_group(group_id)


def update_group_membership_role(user_id: int, group_id: int, role: str) -> bool:
    return _update_group_membership_role(user_id, group_id, role)


def add_group_membership(user_id: int, group_id: int, role: str, created_by: int) -> None:
    _add_group_membership(user_id, group_id, role, created_by)


def list_group_admin_users(group_id: int) -> list[tuple[int, str, str]]:
    return _list_group_admin_users(group_id)


def list_group_viewer_users(group_id: int) -> list[tuple[int, str, str]]:
    return _list_group_viewer_users(group_id)


def remove_user_from_group(user_id: int, group_id: int) -> bool:
    return _remove_user_from_group(user_id, group_id)


def list_pending_group_requests(request_type: str = "join", group_id: int | None = None) -> list[tuple]:
    return _list_pending_group_requests(request_type, group_id)


def get_group_request(request_id: int) -> tuple[int, int, str, str] | None:
    return _get_group_request(request_id)


def set_group_request_status(request_id: int, status: str, reviewed_at: str, reviewed_by: int) -> None:
    _set_group_request_status(request_id, status, reviewed_at, reviewed_by)


def create_group_request(user_id: int, group_id: int, request_type: str, requested_by: int) -> int:
    return _create_group_request(user_id, group_id, request_type, requested_by)


def has_pending_group_role_request(user_id: int, group_id: int, target_role: str) -> bool:
    return _has_pending_group_role_request(user_id, group_id, target_role)


def create_group_role_request(user_id: int, group_id: int, target_role: str, requested_by: int) -> int:
    return _create_group_role_request(user_id, group_id, target_role, requested_by)


def list_pending_group_role_requests(target_role: str, group_id: int | None = None) -> list[tuple]:
    return _list_pending_group_role_requests(target_role, group_id)


def get_group_role_request(request_id: int) -> tuple[int, int, str, str] | None:
    return _get_group_role_request(request_id)


def set_group_role_request_status(request_id: int, status: str, reviewed_at: str, reviewed_by: int) -> None:
    _set_group_role_request_status(request_id, status, reviewed_at, reviewed_by)


def is_group_admin(user_id: int, group_id: int) -> bool:
    return _is_group_admin(user_id, group_id)
