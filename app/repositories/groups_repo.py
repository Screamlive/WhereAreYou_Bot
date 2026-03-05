"""Group-related repository facade."""

from db_repo import (
    get_group_admins as _get_group_admins,
    get_group_membership_role as _get_group_membership_role,
    get_group_members as _get_group_members,
    get_group_name as _get_group_name,
    list_all_groups as _list_all_groups,
    list_pending_group_requests as _list_pending_group_requests,
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


def list_pending_group_requests(request_type: str = "join", group_id: int | None = None) -> list[tuple]:
    return _list_pending_group_requests(request_type, group_id)
