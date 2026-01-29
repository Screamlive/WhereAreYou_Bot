from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram.types import ReplyKeyboardMarkup
else:
    ReplyKeyboardMarkup = Any

from db_repo import (
    get_user_groups,
    get_last_group_id,
    set_last_group_id,
    is_group_admin,
    is_user_admin,
)
from keyboards import (
    superadmin_main_menu,
    group_admin_main_menu,
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


def get_admin_groups(tg_id: int) -> list[tuple[int, str]]:
    return [(gid, name) for gid, name, role in get_user_groups(tg_id) if role == "admin"]


def get_admin_scope(tg_id: int) -> tuple[bool, int | None, bool]:
    """
    Возвращает (есть_доступ, group_id, нужно_выбрать_группу).
    Для суперадмина group_id=None означает глобальный режим.
    """
    if is_superadmin(tg_id):
        return True, get_last_group_id(tg_id), False
    admin_groups = get_admin_groups(tg_id)
    if not admin_groups:
        return False, None, False
    group_id = get_last_group_id(tg_id)
    if not group_id and len(admin_groups) == 1:
        only_gid = admin_groups[0][0]
        set_last_group_id(tg_id, only_gid)
        group_id = only_gid
    if not group_id:
        return False, None, True
    if not is_group_admin(tg_id, group_id):
        return False, None, False
    return True, group_id, False


def get_role_menu(tg_id: int) -> ReplyKeyboardMarkup:
    if is_superadmin(tg_id):
        return superadmin_main_menu
    groups = get_user_groups(tg_id)
    if not groups:
        return no_group_menu
    admin_groups = [(gid, name) for gid, name, role in groups if role == "admin"]
    if admin_groups:
        if len(admin_groups) == 1:
            only_gid = admin_groups[0][0]
            if get_last_group_id(tg_id) != only_gid:
                set_last_group_id(tg_id, only_gid)
            return group_admin_main_menu
        # несколько групп: нужен выбор
        if get_last_group_id(tg_id) in [gid for gid, _ in admin_groups]:
            return group_admin_main_menu
        return group_admin_select_menu
    return user_main_menu
