from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram.types import ReplyKeyboardMarkup
else:
    ReplyKeyboardMarkup = Any

from db_repo import (
    get_user_groups,
    get_last_group_id,
    set_last_group_id,
    get_group_name,
    get_group_membership_role,
    is_user_admin,
)
from keyboards import (
    build_superadmin_main_menu,
    group_admin_main_menu,
    group_viewer_main_menu,
    user_main_menu,
    no_group_menu,
    group_admin_select_menu,
)


def is_superadmin(tg_id: int) -> bool:
    """
    Глобальная роль. Сейчас совпадает с is_admin (переиспользуем колонку).
    """
    return is_user_admin(tg_id)


def user_has_any_group(tg_id: int) -> bool:
    return len(get_user_groups(tg_id)) > 0


def user_is_group_admin_any(tg_id: int) -> bool:
    return any(role == "admin" for _, _, role in get_user_groups(tg_id))


def user_is_group_viewer_any(tg_id: int) -> bool:
    return any(role == "viewer" for _, _, role in get_user_groups(tg_id))


def user_is_group_reader_any(tg_id: int) -> bool:
    return any(role in {"admin", "viewer"} for _, _, role in get_user_groups(tg_id))


def get_admin_groups(tg_id: int) -> list[tuple[int, str]]:
    return [(gid, name) for gid, name, role in get_user_groups(tg_id) if role == "admin"]


def get_view_groups(tg_id: int) -> list[tuple[int, str, str]]:
    return [(gid, name, role) for gid, name, role in get_user_groups(tg_id) if role in {"admin", "viewer"}]


def get_group_scope(tg_id: int) -> tuple[bool, bool, int | None, bool]:
    """
    Возвращает (can_read, can_write, group_id, need_select_group).
    Для суперадмина can_read/can_write всегда True, group_id может быть None (глобально).
    """
    if is_superadmin(tg_id):
        return True, True, get_last_group_id(tg_id), False

    view_groups = get_view_groups(tg_id)
    if not view_groups:
        return False, False, None, False

    group_id = get_last_group_id(tg_id)
    if not group_id and len(view_groups) == 1:
        only_gid = view_groups[0][0]
        set_last_group_id(tg_id, only_gid)
        group_id = only_gid

    allowed_group_ids = {gid for gid, _name, _role in view_groups}
    if not group_id or group_id not in allowed_group_ids:
        return False, False, None, True

    role = get_group_membership_role(tg_id, group_id)
    if role not in {"admin", "viewer"}:
        return False, False, None, False

    can_write = role == "admin"
    return True, can_write, group_id, False


def get_admin_scope(tg_id: int) -> tuple[bool, int | None, bool]:
    """
    Возвращает (есть_доступ, group_id, нужно_выбрать_группу).
    Для суперадмина group_id=None означает глобальный режим.
    """
    can_read, can_write, group_id, need_select = get_group_scope(tg_id)
    if not can_read:
        return False, None, need_select
    if not can_write:
        return False, None, False
    return True, group_id, False


def get_role_menu(tg_id: int) -> ReplyKeyboardMarkup:
    if is_superadmin(tg_id):
        group_id = get_last_group_id(tg_id)
        scope_name = "глобально"
        if group_id:
            scope_name = get_group_name(group_id) or f"ID={group_id}"
        return build_superadmin_main_menu(scope_name)
    groups = get_user_groups(tg_id)
    if not groups:
        return no_group_menu

    managed_groups = [(gid, name, role) for gid, name, role in groups if role in {"admin", "viewer"}]
    if managed_groups:
        if len(managed_groups) == 1:
            only_gid, _only_name, only_role = managed_groups[0]
            if get_last_group_id(tg_id) != only_gid:
                set_last_group_id(tg_id, only_gid)
            return group_admin_main_menu if only_role == "admin" else group_viewer_main_menu

        selected_gid = get_last_group_id(tg_id)
        if selected_gid in [gid for gid, _name, _role in managed_groups]:
            selected_role = get_group_membership_role(tg_id, selected_gid)
            return group_admin_main_menu if selected_role == "admin" else group_viewer_main_menu
        return group_admin_select_menu

    return user_main_menu
