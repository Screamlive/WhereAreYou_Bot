import datetime

from aiogram import Bot, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from core import (
    is_superadmin,
    get_group_scope,
    get_admin_scope,
    get_view_groups,
    get_role_menu,
)
from db_repo import (
    log_action,
    get_admins,
    list_all_groups,
    get_group_name,
    get_group_members,
    get_group_admins,
    user_exists_in_db,
    is_user_approved,
    user_in_group,
    has_pending_group_request,
    create_group,
    delete_group,
    get_group_membership_role,
    update_group_membership_role,
    add_group_membership,
    list_group_admin_users,
    list_group_viewer_users,
    remove_user_from_group,
    list_pending_group_requests,
    get_group_request,
    set_group_request_status,
    create_group_request,
    has_pending_group_role_request,
    create_group_role_request,
    list_pending_group_role_requests,
    get_group_role_request,
    set_group_role_request_status,
    get_approved_users,
    get_all_users,
    get_user_fullname,
    get_user_groups,
    get_last_group_id,
    set_last_group_id,
    is_group_admin,
)
from texts import (
    TEXT_NO_RIGHTS,
    TEXT_NO_RIGHTS_ALERT,
    TEXT_SELECT_GROUP_FIRST,
    TEXT_SELECT_GROUP_FIRST_ALERT,
    TEXT_GROUPS_NOT_FOUND,
    TEXT_INVALID_GROUP,
    TEXT_GROUP_NOT_FOUND,
    TEXT_INVALID_USER,
    TEXT_GROUP_NOT_SELECTED,
    TEXT_USER_ALREADY_GROUP_ADMIN,
    TEXT_MENU_UPDATED,
    TEXT_NO_APPROVED_USERS,
    TEXT_USER_NOT_IN_GROUP,
    TEXT_REQUEST_NOT_FOUND,
    TEXT_INVALID_REQUEST,
    TEXT_CANCEL_BUTTON,
    TEXT_GROUP_NO_USERS,
    TEXT_REQUEST_ALREADY_PENDING,
    TEXT_NOT_APPROVED_SHORT,
    TEXT_NOT_REGISTERED_SHORT,
    TEXT_SELECT_GROUP,
    TEXT_SELECT_USER,
    TEXT_NO_GROUPS_YET,
)

router = Router()
bot: Bot | None = None

GROUP_ADD_PAGE_SIZE = 10


def set_bot(bot_instance: Bot) -> None:
    global bot
    bot = bot_instance


def _paginate_users(
    users: list[tuple[int, str, str]],
    page: int,
    page_size: int = GROUP_ADD_PAGE_SIZE
) -> tuple[list[tuple[int, str, str]], int, int]:
    if not users:
        return [], 0, 0
    total_pages = (len(users) + page_size - 1) // page_size
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * page_size
    return users[start:start + page_size], safe_page, total_pages


def _toggle_selected_user(selected_ids: list[int], user_id: int) -> list[int]:
    selected = set(selected_ids)
    if user_id in selected:
        selected.remove(user_id)
    else:
        selected.add(user_id)
    return sorted(selected)


def _build_group_add_users_picker(
    group_id: int,
    users: list[tuple[int, str, str]],
    selected_ids: list[int],
    page: int
) -> tuple[str, InlineKeyboardMarkup]:
    group_name = get_group_name(group_id) or f"ID={group_id}"
    page_users, safe_page, total_pages = _paginate_users(users, page)
    selected_set = set(selected_ids)

    text = (
        f"Группа: {group_name}\n"
        f"Выбрано: {len(selected_ids)}\n"
        f"Страница: {safe_page + 1}/{max(total_pages, 1)}\n\n"
        "Отметьте сотрудников и нажмите «Готово».\n"
        "Пользователи, которые уже в группе, будут пропущены."
    )

    kb_rows: list[list[InlineKeyboardButton]] = []
    for uid, fullname, username in page_users:
        uname = f" (@{username})" if username else ""
        in_group = get_group_membership_role(uid, group_id) is not None
        marker = "✅" if uid in selected_set else "⬜"
        suffix = " • уже в группе" if in_group else ""
        label = f"{marker} {fullname}{uname}{suffix}"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"gm_toggle:{uid}")])

    nav_row: list[InlineKeyboardButton] = []
    if total_pages > 1:
        if safe_page > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"gm_page:{safe_page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data="gm_noop"))
        if safe_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="Следующая ➡️", callback_data=f"gm_page:{safe_page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="Следующая ➡️", callback_data="gm_noop"))
    if nav_row:
        kb_rows.append(nav_row)

    kb_rows.append([InlineKeyboardButton(text="Готово ✅", callback_data="gm_apply")])
    kb_rows.append([
        InlineKeyboardButton(text="Сбросить выбор", callback_data="gm_reset"),
        InlineKeyboardButton(text=TEXT_CANCEL_BUTTON, callback_data="gm_cancel"),
    ])

    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)


def _group_role_label(role: str) -> str:
    if role == "admin":
        return "админ"
    if role == "viewer":
        return "наблюдатель"
    return "участник"


###############################################################################
# Группы (суперадмин)
###############################################################################
class GroupCreateFSM(StatesGroup):
    waiting_for_name = State()


@router.message(lambda msg: msg.text == "Создать группу")
async def create_group_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer("Введите название группы:", reply_markup=cancel_kb)
    await state.set_state(GroupCreateFSM.waiting_for_name)


@router.message(GroupCreateFSM.waiting_for_name)
async def create_group_finish(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Пустое название. Попробуйте снова.")
        return

    if create_group(name, message.from_user.id):
        await message.answer(f"Группа создана: {name}", reply_markup=get_role_menu(message.from_user.id))
    else:
        await message.answer("Такая группа уже существует.", reply_markup=get_role_menu(message.from_user.id))

    await state.clear()


@router.message(lambda msg: msg.text == "Список групп")
async def list_groups(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    text = "Группы:\n" + "\n".join([f"- {name} (ID={gid})" for gid, name in groups])
    await message.answer(text)


###############################################################################
# Суперадмин: удалить группу
###############################################################################
@router.message(lambda msg: msg.text == "Удалить группу")
async def delete_group_start(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"del_group_pick:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите группу для удаления:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("del_group_pick:"))
async def delete_group_confirm(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Удалить группу", callback_data=f"del_group_confirm:{group_id}"),
        InlineKeyboardButton(text=TEXT_CANCEL_BUTTON, callback_data="del_group_cancel")
    ]])
    await cb.message.answer(
        f"Подтвердите удаление группы «{group_name}».",
        reply_markup=kb
    )
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("del_group_confirm:"))
async def delete_group_confirmed(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    delete_group(group_id)

    log_action(cb.from_user.id, f"delete_group {group_id}")
    await cb.message.answer(f"Группа «{group_name}» удалена.", reply_markup=get_role_menu(cb.from_user.id))
    await cb.answer()


@router.callback_query(lambda c: c.data == "del_group_cancel")
async def delete_group_cancel(cb: CallbackQuery):
    await cb.message.answer("Удаление группы отменено.")
    await cb.answer()


###############################################################################
# Список администраторов группы
###############################################################################
@router.message(lambda msg: msg.text in {"Список администраторов группы", "Список админов группы"})
async def list_group_admins_cmd(message: types.Message):
    tg_id = message.from_user.id
    can_read, _can_write, group_id, need_select = get_group_scope(tg_id)
    if not can_read:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS)
        return
    if not group_id:
        await message.answer(TEXT_SELECT_GROUP_FIRST)
        return

    rows = list_group_admin_users(group_id)

    group_name = get_group_name(group_id) or f"ID={group_id}"
    if not rows:
        await message.answer(f"В группе «{group_name}» нет администраторов.")
        return

    lines = [f"Администраторы группы «{group_name}»:"] 
    for uid, fullname, username in rows:
        uname = f" (@{username})" if username else ""
        lines.append(f"- {fullname}{uname} (ID={uid})")
    await message.answer("\n".join(lines))


###############################################################################
# Суперадмин: список пользователей группы
###############################################################################
@router.message(lambda msg: msg.text in {"Список пользователей группы", "Состав группы"})
async def superadmin_list_group_users_start(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"list_group_users:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите группу:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("list_group_users:"))
async def superadmin_list_group_users_pick(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    rows = get_group_members(group_id)
    if not rows:
        await cb.message.answer(f"В группе «{group_name}» нет пользователей.")
        await cb.answer()
        return

    lines = [f"Пользователи группы «{group_name}»:"] 
    for uid, fullname, username, role in rows:
        uname = f" (@{username})" if username else ""
        role_label = _group_role_label(role)
        lines.append(f"- {fullname}{uname} [{role_label}] (ID={uid})")
    await cb.message.answer("\n".join(lines))
    await cb.answer()


###############################################################################
# Назначить/отозвать администратора группы
###############################################################################
class GroupAdminAssignFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@router.message(lambda msg: msg.text in {"Назначить админа группы", "Назначить администратора группы"})
async def assign_group_admin_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(TEXT_SELECT_GROUP, reply_markup=cancel_kb)

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"ga_group:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Группа для назначения администратора:", reply_markup=inline_kb)
    await state.set_state(GroupAdminAssignFSM.waiting_for_group)


@router.callback_query(lambda c: c.data.startswith("ga_group:"), GroupAdminAssignFSM.waiting_for_group)
async def assign_group_admin_pick_group(cb: CallbackQuery, state: FSMContext):
    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    await state.update_data(group_id=group_id)

    users = get_approved_users()
    if not users:
        await cb.message.answer(TEXT_NO_APPROVED_USERS)
        await cb.answer()
        await state.clear()
        return

    kb_rows = []
    for uid, fullname, username in users:
        label = f"{fullname}"
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"ga_user:{uid}")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)
    await state.set_state(GroupAdminAssignFSM.waiting_for_user)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("ga_user:"), GroupAdminAssignFSM.waiting_for_user)
async def assign_group_admin_pick_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    role = get_group_membership_role(user_id, group_id)

    if role:
        if role == "admin":
            msg = TEXT_USER_ALREADY_GROUP_ADMIN
        else:
            update_group_membership_role(user_id, group_id, "admin")
            msg = "Роль пользователя обновлена на админа группы."
            try:
                group_name = get_group_name(group_id) or f"ID={group_id}"
                await bot.send_message(
                    user_id,
                    f"Вам назначена роль администратора группы: {group_name}."
                )
                await bot.send_message(
                    user_id,
                    TEXT_MENU_UPDATED,
                    reply_markup=get_role_menu(user_id)
                )
            except Exception:
                pass
    else:
        add_group_membership(user_id, group_id, "admin", cb.from_user.id)
        msg = "Пользователь назначен админом группы."
        try:
            group_name = get_group_name(group_id) or f"ID={group_id}"
            await bot.send_message(
                user_id,
                f"Вы добавлены в группу {group_name} как администратор."
            )
            await bot.send_message(
                user_id,
                TEXT_MENU_UPDATED,
                reply_markup=get_role_menu(user_id)
            )
        except Exception:
            pass

    await cb.message.answer(msg, reply_markup=get_role_menu(cb.from_user.id))
    await cb.answer()
    await state.clear()


class GroupAdminRevokeFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@router.message(lambda msg: msg.text in {"Отозвать администратора группы", "Отозвать админа группы"})
async def revoke_group_admin_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(TEXT_SELECT_GROUP, reply_markup=cancel_kb)

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"gar_group:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Группа для отзыва прав администратора:", reply_markup=inline_kb)
    await state.set_state(GroupAdminRevokeFSM.waiting_for_group)


@router.callback_query(lambda c: c.data.startswith("gar_group:"), GroupAdminRevokeFSM.waiting_for_group)
async def revoke_group_admin_pick_group(cb: CallbackQuery, state: FSMContext):
    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    await state.update_data(group_id=group_id)

    rows = list_group_admin_users(group_id)
    if not rows:
        await cb.message.answer("В этой группе нет администраторов.")
        await cb.answer()
        await state.clear()
        return

    kb_rows = []
    for uid, fullname, username in rows:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"gar_user:{uid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer("Выберите администратора для отзыва прав:", reply_markup=inline_kb)
    await state.set_state(GroupAdminRevokeFSM.waiting_for_user)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("gar_user:"), GroupAdminRevokeFSM.waiting_for_user)
async def revoke_group_admin_pick_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    role = get_group_membership_role(user_id, group_id)
    if not role or role != "admin":
        await cb.answer("Пользователь не является администратором этой группы.", show_alert=True)
        await state.clear()
        return

    update_group_membership_role(user_id, group_id, "member")

    group_name = get_group_name(group_id) or f"ID={group_id}"
    log_action(cb.from_user.id, f"revoke_group_admin {user_id} group={group_id}")
    await cb.message.answer(f"Права администратора группы отозваны: {get_user_fullname(user_id)}.")
    try:
        await bot.send_message(
            user_id,
            f"У вас отозвали права администратора группы «{group_name}».",
            reply_markup=get_role_menu(user_id)
        )
    except Exception:
        pass
    await cb.answer()
    await state.clear()


class GroupViewerAssignFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


class GroupViewerRevokeFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


async def _send_viewer_candidates(cb: CallbackQuery, state: FSMContext, group_id: int) -> None:
    members = get_group_members(group_id)
    if not members:
        await cb.message.answer(TEXT_GROUP_NO_USERS)
        await state.clear()
        return

    await state.update_data(group_id=group_id)
    kb_rows = []
    for uid, fullname, username, role in members:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        label += f" [{_group_role_label(role)}]"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"gva_user:{uid}")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer("Выберите пользователя для назначения роли наблюдателя:", reply_markup=inline_kb)
    await state.set_state(GroupViewerAssignFSM.waiting_for_user)


@router.message(lambda msg: msg.text == "Назначить наблюдателя")
async def assign_group_viewer_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if is_superadmin(user_id):
        groups = list_all_groups()
        if not groups:
            await message.answer(TEXT_GROUPS_NOT_FOUND)
            return
        await state.clear()
        kb_rows = []
        for gid, name in groups:
            kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"gva_group:{gid}")])
        await message.answer(
            "Выберите группу для назначения роли наблюдателя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
        )
        await state.set_state(GroupViewerAssignFSM.waiting_for_group)
        return

    allowed, group_id, need_select = get_admin_scope(user_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS)
        return
    if not group_id:
        await message.answer(TEXT_SELECT_GROUP_FIRST)
        return

    members = get_group_members(group_id)
    if not members:
        await message.answer(TEXT_GROUP_NO_USERS)
        return

    await state.clear()
    await state.update_data(group_id=group_id)
    kb_rows = []
    for uid, fullname, username, role in members:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        label += f" [{_group_role_label(role)}]"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"gva_user:{uid}")])
    await message.answer(
        "Выберите пользователя для назначения роли наблюдателя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await state.set_state(GroupViewerAssignFSM.waiting_for_user)


@router.callback_query(lambda c: c.data.startswith("gva_group:"), GroupViewerAssignFSM.waiting_for_group)
async def assign_group_viewer_pick_group(cb: CallbackQuery, state: FSMContext):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        await state.clear()
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    await _send_viewer_candidates(cb, state, group_id)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("gva_user:"), GroupViewerAssignFSM.waiting_for_user)
async def assign_group_viewer_pick_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    reviewer_id = cb.from_user.id
    if not is_superadmin(reviewer_id) and not is_group_admin(reviewer_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    role = get_group_membership_role(user_id, group_id)
    if role == "admin":
        msg = "Пользователь уже администратор группы."
    elif role == "viewer":
        msg = "Пользователь уже наблюдатель группы."
    elif role == "member":
        update_group_membership_role(user_id, group_id, "viewer")
        msg = "Роль пользователя обновлена на наблюдателя."
    else:
        add_group_membership(user_id, group_id, "viewer", reviewer_id)
        msg = "Пользователь добавлен как наблюдатель."

    group_name = get_group_name(group_id) or f"ID={group_id}"
    await cb.message.answer(msg, reply_markup=get_role_menu(reviewer_id))
    if bot:
        try:
            await bot.send_message(
                user_id,
                f"Вам назначена роль наблюдателя в группе «{group_name}».",
            )
            await bot.send_message(
                user_id,
                TEXT_MENU_UPDATED,
                reply_markup=get_role_menu(user_id)
            )
        except Exception:
            pass
    log_action(reviewer_id, f"assign_group_viewer user={user_id} group={group_id}")
    await cb.answer()
    await state.clear()


@router.message(lambda msg: msg.text == "Снять наблюдателя")
async def revoke_group_viewer_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if is_superadmin(user_id):
        groups = list_all_groups()
        if not groups:
            await message.answer(TEXT_GROUPS_NOT_FOUND)
            return
        await state.clear()
        kb_rows = []
        for gid, name in groups:
            kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"gvr_group:{gid}")])
        await message.answer(
            "Выберите группу для отзыва роли наблюдателя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
        )
        await state.set_state(GroupViewerRevokeFSM.waiting_for_group)
        return

    allowed, group_id, need_select = get_admin_scope(user_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS)
        return
    if not group_id:
        await message.answer(TEXT_SELECT_GROUP_FIRST)
        return

    viewers = list_group_viewer_users(group_id)
    if not viewers:
        await message.answer("В этой группе нет наблюдателей.")
        return

    await state.clear()
    await state.update_data(group_id=group_id)
    kb_rows = []
    for uid, fullname, username in viewers:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"gvr_user:{uid}")])
    await message.answer(
        "Выберите наблюдателя для отзыва роли:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await state.set_state(GroupViewerRevokeFSM.waiting_for_user)


@router.callback_query(lambda c: c.data.startswith("gvr_group:"), GroupViewerRevokeFSM.waiting_for_group)
async def revoke_group_viewer_pick_group(cb: CallbackQuery, state: FSMContext):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        await state.clear()
        return
    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    viewers = list_group_viewer_users(group_id)
    if not viewers:
        await cb.message.answer("В этой группе нет наблюдателей.")
        await cb.answer()
        await state.clear()
        return

    await state.update_data(group_id=group_id)
    kb_rows = []
    for uid, fullname, username in viewers:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"gvr_user:{uid}")])
    await cb.message.answer(
        "Выберите наблюдателя для отзыва роли:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await state.set_state(GroupViewerRevokeFSM.waiting_for_user)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("gvr_user:"), GroupViewerRevokeFSM.waiting_for_user)
async def revoke_group_viewer_pick_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    reviewer_id = cb.from_user.id
    if not is_superadmin(reviewer_id) and not is_group_admin(reviewer_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    role = get_group_membership_role(user_id, group_id)
    if role != "viewer":
        await cb.answer("Пользователь не является наблюдателем этой группы.", show_alert=True)
        await state.clear()
        return

    update_group_membership_role(user_id, group_id, "member")
    group_name = get_group_name(group_id) or f"ID={group_id}"
    await cb.message.answer("Роль наблюдателя отозвана.", reply_markup=get_role_menu(reviewer_id))
    if bot:
        try:
            await bot.send_message(
                user_id,
                f"В группе «{group_name}» у вас отозвали роль наблюдателя.",
            )
            await bot.send_message(
                user_id,
                TEXT_MENU_UPDATED,
                reply_markup=get_role_menu(user_id)
            )
        except Exception:
            pass
    log_action(reviewer_id, f"revoke_group_viewer user={user_id} group={group_id}")
    await cb.answer()
    await state.clear()


class GroupAddUserFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@router.message(lambda msg: msg.text in {"Добавить пользователя в группу", "Добавить в группу"})
async def add_user_to_group_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(TEXT_SELECT_GROUP, reply_markup=cancel_kb)

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"gm_group:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Группа для добавления пользователя:", reply_markup=inline_kb)
    await state.set_state(GroupAddUserFSM.waiting_for_group)


@router.callback_query(lambda c: c.data.startswith("gm_group:"), GroupAddUserFSM.waiting_for_group)
async def add_user_to_group_pick_group(cb: CallbackQuery, state: FSMContext):
    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        await state.clear()
        return

    users = get_approved_users()
    if not users:
        await cb.message.answer(TEXT_NO_APPROVED_USERS)
        await cb.answer()
        await state.clear()
        return

    await state.update_data(
        gm_group_id=group_id,
        gm_selected=[],
        gm_page=0,
    )
    picker_text, picker_kb = _build_group_add_users_picker(group_id, users, [], 0)
    await cb.message.answer(picker_text, reply_markup=picker_kb)
    await state.set_state(GroupAddUserFSM.waiting_for_user)
    await cb.answer()


@router.callback_query(lambda c: c.data == "gm_noop", GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("gm_page:"), GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_change_page(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("gm_group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    try:
        next_page = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_REQUEST, show_alert=True)
        return

    users = get_approved_users()
    if not users:
        await cb.message.edit_text(TEXT_NO_APPROVED_USERS, reply_markup=None)
        await cb.answer()
        await state.clear()
        return

    current_page = data.get("gm_page", 0)
    _rows, safe_page, _total_pages = _paginate_users(users, next_page)
    if safe_page == current_page:
        await cb.answer()
        return

    selected_ids = data.get("gm_selected", [])
    picker_text, picker_kb = _build_group_add_users_picker(group_id, users, selected_ids, safe_page)
    await state.update_data(gm_page=safe_page)
    await cb.message.edit_text(picker_text, reply_markup=picker_kb)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("gm_toggle:"), GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_toggle_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("gm_group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    selected_ids = _toggle_selected_user(data.get("gm_selected", []), user_id)
    page = data.get("gm_page", 0)
    users = get_approved_users()
    if not users:
        await cb.message.edit_text(TEXT_NO_APPROVED_USERS, reply_markup=None)
        await cb.answer()
        await state.clear()
        return

    await state.update_data(gm_selected=selected_ids)
    _rows, safe_page, _total_pages = _paginate_users(users, page)
    picker_text, picker_kb = _build_group_add_users_picker(group_id, users, selected_ids, safe_page)
    await state.update_data(gm_page=safe_page)
    await cb.message.edit_text(picker_text, reply_markup=picker_kb)
    await cb.answer()


@router.callback_query(lambda c: c.data == "gm_reset", GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_reset_selection(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("gm_group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    selected_ids = data.get("gm_selected", [])
    if not selected_ids:
        await cb.answer("Выбор уже пуст.")
        return

    page = data.get("gm_page", 0)
    users = get_approved_users()
    if not users:
        await cb.message.edit_text(TEXT_NO_APPROVED_USERS, reply_markup=None)
        await cb.answer()
        await state.clear()
        return

    await state.update_data(gm_selected=[])
    _rows, safe_page, _total_pages = _paginate_users(users, page)
    picker_text, picker_kb = _build_group_add_users_picker(group_id, users, [], safe_page)
    await state.update_data(gm_page=safe_page)
    await cb.message.edit_text(picker_text, reply_markup=picker_kb)
    await cb.answer("Выбор сброшен.")


@router.callback_query(lambda c: c.data == "gm_apply", GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_apply_selection(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("gm_group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    selected_ids = data.get("gm_selected", [])
    if not selected_ids:
        await cb.answer("Сначала выберите хотя бы одного пользователя.", show_alert=True)
        return

    added_ids: list[int] = []
    skipped_member = 0
    skipped_admin = 0
    errors = 0

    for user_id in selected_ids:
        role = get_group_membership_role(user_id, group_id)
        if role == "admin":
            skipped_admin += 1
            continue
        if role:
            skipped_member += 1
            continue
        try:
            add_group_membership(user_id, group_id, "member", cb.from_user.id)
            added_ids.append(user_id)
        except Exception:
            errors += 1

    group_name = get_group_name(group_id) or f"ID={group_id}"
    if bot:
        for user_id in added_ids:
            try:
                await bot.send_message(
                    user_id,
                    f"Вы добавлены в группу {group_name}."
                )
                await bot.send_message(
                    user_id,
                    TEXT_MENU_UPDATED,
                    reply_markup=get_role_menu(user_id)
                )
            except Exception:
                pass

    await cb.message.answer(
        "Итог добавления:\n"
        f"Группа: {group_name}\n"
        f"Добавлено: {len(added_ids)}\n"
        f"Пропущено (уже участник): {skipped_member}\n"
        f"Пропущено (уже админ): {skipped_admin}\n"
        f"Ошибки: {errors}"
    )
    log_action(
        cb.from_user.id,
        (
            f"bulk_add_users group={group_id} "
            f"added={len(added_ids)} skipped_member={skipped_member} "
            f"skipped_admin={skipped_admin} errors={errors}"
        )
    )

    users = get_approved_users()
    await state.update_data(gm_selected=[], gm_page=0)
    if not users:
        await cb.message.edit_text(TEXT_NO_APPROVED_USERS, reply_markup=None)
        await cb.answer()
        await state.clear()
        return

    picker_text, picker_kb = _build_group_add_users_picker(group_id, users, [], 0)
    await cb.message.edit_text(picker_text, reply_markup=picker_kb)
    await cb.answer()


@router.callback_query(lambda c: c.data == "gm_cancel", GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Добавление пользователей в группу завершено.", reply_markup=get_role_menu(cb.from_user.id))
    await cb.answer()


class GroupRemoveUserFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@router.message(lambda msg: msg.text in {"Удалить пользователя из группы", "Удалить из группы"} and is_superadmin(msg.from_user.id))
async def remove_user_from_group_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(TEXT_SELECT_GROUP, reply_markup=cancel_kb)

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"grm_group:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Группа для удаления пользователя:", reply_markup=inline_kb)
    await state.set_state(GroupRemoveUserFSM.waiting_for_group)


@router.callback_query(lambda c: c.data.startswith("grm_group:"), GroupRemoveUserFSM.waiting_for_group)
async def remove_user_from_group_pick_group(cb: CallbackQuery, state: FSMContext):
    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    await state.update_data(group_id=group_id)

    members = get_group_members(group_id)
    if not members:
        await cb.message.answer("В группе нет пользователей.")
        await cb.answer()
        await state.clear()
        return

    kb_rows = []
    for uid, fullname, username, role in members:
        label = f"{fullname}"
        if username:
            label += f" (@{username})"
        role_label = _group_role_label(role)
        label += f" [{role_label}]"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"grm_user:{uid}")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer("Выберите пользователя для удаления из группы:", reply_markup=inline_kb)
    await state.set_state(GroupRemoveUserFSM.waiting_for_user)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("grm_user:"), GroupRemoveUserFSM.waiting_for_user)
async def remove_user_from_group_pick_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await cb.answer(TEXT_GROUP_NOT_SELECTED, show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    deleted = remove_user_from_group(user_id, group_id)

    if not deleted:
        await cb.message.answer(TEXT_USER_NOT_IN_GROUP, reply_markup=get_role_menu(cb.from_user.id))
        await cb.answer()
        await state.clear()
        return

    group_name = get_group_name(group_id) or f"ID={group_id}"
    await cb.message.answer(f"Пользователь удалён из группы {group_name}.", reply_markup=get_role_menu(cb.from_user.id))
    try:
        await bot.send_message(
            user_id,
            f"Вы удалены из группы {group_name}.",
            reply_markup=get_role_menu(user_id)
        )
    except Exception:
        pass
    await cb.answer()
    await state.clear()


###############################################################################
# Заявки в группу (админ группы / суперадмин)
###############################################################################
@router.message(lambda msg: msg.text in {"Заявки на вступление", "Заявки на выход"})
async def show_group_requests(message: types.Message):
    user_id = message.from_user.id
    can_read, can_write, group_id, need_select = get_group_scope(user_id)
    if not can_read:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS)
        return

    req_type = "join" if "вступление" in message.text else "leave"

    rows = list_pending_group_requests(req_type, group_id)

    if not rows:
        empty_label = "вступление" if req_type == "join" else "выход"
        await message.answer(f"Нет заявок на {empty_label}.")
        return

    for req_id, req_user_id, fullname, username, gid, gname, req_type in rows:
        user_disp = fullname
        if username:
            user_disp += f" (@{username})"
        type_label = "вступление" if req_type == "join" else "выход"
        text = (
            f"Заявка #{req_id}\n"
            f"Группа: {gname} (ID={gid})\n"
            f"Тип: {type_label}\n"
            f"Пользователь: {user_disp} (ID={req_user_id})"
        )
        if can_write:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Одобрить", callback_data=f"grp_req_approve:{req_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"grp_req_decline:{req_id}")
            ]])
            await message.answer(text, reply_markup=kb)
        else:
            await message.answer(text + "\n(режим наблюдателя: только просмотр)")


@router.message(lambda msg: msg.text == "Заявки на роль")
async def show_group_role_requests(message: types.Message):
    user_id = message.from_user.id
    can_read, can_write, group_id, need_select = get_group_scope(user_id)
    if not can_read:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS)
        return

    rows = list_pending_group_role_requests("viewer", group_id)
    if not rows:
        await message.answer("Нет заявок на роль наблюдателя.")
        return

    for req_id, req_user_id, fullname, username, gid, gname, _target_role in rows:
        user_disp = fullname
        if username:
            user_disp += f" (@{username})"
        text = (
            f"Заявка на роль #{req_id}\n"
            f"Группа: {gname} (ID={gid})\n"
            f"Роль: наблюдатель\n"
            f"Пользователь: {user_disp} (ID={req_user_id})"
        )
        if can_write:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Одобрить", callback_data=f"grp_role_approve:{req_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"grp_role_decline:{req_id}")
            ]])
            await message.answer(text, reply_markup=kb)
        else:
            await message.answer(text + "\n(режим наблюдателя: только просмотр)")


@router.callback_query(lambda c: c.data.startswith("grp_req_approve:") or c.data.startswith("grp_req_decline:"))
async def handle_group_request(cb: CallbackQuery):
    user_id = cb.from_user.id
    action, req_id_str = cb.data.split(":", 1)
    try:
        req_id = int(req_id_str)
    except ValueError:
        await cb.answer(TEXT_INVALID_REQUEST, show_alert=True)
        return

    row = get_group_request(req_id)
    if not row:
        await cb.answer(TEXT_REQUEST_NOT_FOUND, show_alert=True)
        return

    req_user_id, group_id, req_type, status = row
    if status != "pending":
        await cb.answer("Заявка уже обработана.", show_alert=True)
        return

    if not is_superadmin(user_id) and not is_group_admin(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    group_name = get_group_name(group_id) or f"ID={group_id}"
    now = datetime.datetime.now().isoformat()

    if action == "grp_req_approve":
        if req_type == "join":
            if not user_in_group(req_user_id, group_id):
                add_group_membership(req_user_id, group_id, "member", user_id)
        elif req_type == "leave":
            remove_user_from_group(req_user_id, group_id)

        set_group_request_status(req_id, "approved", now, user_id)

        await cb.message.answer(f"Заявка #{req_id} одобрена.")
        try:
            await bot.send_message(
                req_user_id,
                f"Ваш запрос на {('вступление в группу' if req_type == 'join' else 'выход из группы')} "
                f"«{group_name}» одобрен."
            )
            await bot.send_message(
                req_user_id,
                "Ваше меню обновлено.",
                reply_markup=get_role_menu(req_user_id)
            )
        except Exception:
            pass
        await cb.answer()
        log_action(user_id, f"group_request approved {req_id}")
        return

    # decline
    set_group_request_status(req_id, "declined", now, user_id)

    await cb.message.answer(f"Заявка #{req_id} отклонена.")
    try:
        await bot.send_message(
            req_user_id,
            f"Ваш запрос на {('вступление в группу' if req_type == 'join' else 'выход из группы')} "
            f"«{group_name}» отклонён."
        )
    except Exception:
        pass
    await cb.answer()
    log_action(user_id, f"group_request declined {req_id}")


@router.callback_query(lambda c: c.data.startswith("grp_role_approve:") or c.data.startswith("grp_role_decline:"))
async def handle_group_role_request(cb: CallbackQuery):
    reviewer_id = cb.from_user.id
    action, req_id_str = cb.data.split(":", 1)
    try:
        req_id = int(req_id_str)
    except ValueError:
        await cb.answer(TEXT_INVALID_REQUEST, show_alert=True)
        return

    row = get_group_role_request(req_id)
    if not row:
        await cb.answer(TEXT_REQUEST_NOT_FOUND, show_alert=True)
        return

    req_user_id, group_id, target_role, status = row
    if status != "pending":
        await cb.answer("Заявка уже обработана.", show_alert=True)
        return

    if not is_superadmin(reviewer_id) and not is_group_admin(reviewer_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    now = datetime.datetime.now().isoformat()
    group_name = get_group_name(group_id) or f"ID={group_id}"

    if action == "grp_role_approve":
        current_role = get_group_membership_role(req_user_id, group_id)
        if current_role == "admin":
            result_text = "Пользователь уже администратор группы."
        elif current_role == "viewer":
            result_text = "Пользователь уже наблюдатель группы."
        elif current_role == "member":
            update_group_membership_role(req_user_id, group_id, "viewer")
            result_text = "Роль пользователя обновлена: наблюдатель."
        else:
            add_group_membership(req_user_id, group_id, "viewer", reviewer_id)
            result_text = "Пользователь добавлен в группу как наблюдатель."

        set_group_role_request_status(req_id, "approved", now, reviewer_id)
        await cb.message.answer(f"Заявка на роль #{req_id} одобрена. {result_text}")
        if bot:
            try:
                await bot.send_message(
                    req_user_id,
                    f"Ваша заявка на роль наблюдателя в группе «{group_name}» одобрена."
                )
                await bot.send_message(
                    req_user_id,
                    TEXT_MENU_UPDATED,
                    reply_markup=get_role_menu(req_user_id)
                )
            except Exception:
                pass
        log_action(reviewer_id, f"group_role_request approved {req_id}")
        await cb.answer()
        return

    set_group_role_request_status(req_id, "declined", now, reviewer_id)
    await cb.message.answer(f"Заявка на роль #{req_id} отклонена.")
    if bot:
        try:
            await bot.send_message(
                req_user_id,
                f"Ваша заявка на роль наблюдателя в группе «{group_name}» отклонена."
            )
        except Exception:
            pass
    log_action(reviewer_id, f"group_role_request declined {req_id}")
    await cb.answer()


###############################################################################
# Сменить рабочую группу (админ/суперадмин)
###############################################################################
@router.message(lambda msg: msg.text in {"Сменить группу", "Выбрать группу"})
async def change_work_group(message: types.Message):
    user_id = message.from_user.id

    view_groups = get_view_groups(user_id)

    if not is_superadmin(user_id) and not view_groups:
        await message.answer(TEXT_NO_RIGHTS)
        return

    if is_superadmin(user_id):
        groups = list_all_groups()
        allow_global = True
    else:
        groups = [(gid, name) for (gid, name, _role) in view_groups]
        allow_global = False

    if not groups and not allow_global:
        await message.answer(TEXT_GROUPS_NOT_FOUND)
        return

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"set_group:{gid}")])

    if allow_global:
        kb_rows.append([InlineKeyboardButton(text="Глобально", callback_data="set_group:global")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите рабочую группу:", reply_markup=inline_kb)


@router.message(lambda msg: msg.text == "Глобально")
async def set_work_group_global(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    set_last_group_id(message.from_user.id, None)
    await message.answer(
        "Режим суперадмина: глобально. Права не изменены, групповой фильтр сброшен.",
        reply_markup=get_role_menu(message.from_user.id)
    )


@router.callback_query(lambda c: c.data.startswith("set_group:"))
async def set_work_group(cb: CallbackQuery):
    user_id = cb.from_user.id
    payload = cb.data.split(":", 1)[1]

    if payload == "global":
        if not is_superadmin(user_id):
            await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
            return
        set_last_group_id(user_id, None)
        await cb.message.answer("Режим суперадмина: глобально. Права не изменены, фильтр сброшен.")
        await cb.answer()
        return

    try:
        group_id = int(payload)
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    if not is_superadmin(user_id) and get_group_membership_role(user_id, group_id) not in {"admin", "viewer"}:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    if not set_last_group_id(user_id, group_id):
        await cb.answer("Пользователь не найден.", show_alert=True)
        return

    if is_superadmin(user_id):
        await cb.message.answer(
            f"Режим суперадмина: фильтр по группе «{group_name}». Права не изменены."
        )
    else:
        await cb.message.answer(f"Рабочая группа установлена: {group_name}")
    # Обновим меню после выбора группы
    await cb.message.answer(TEXT_MENU_UPDATED, reply_markup=get_role_menu(user_id))
    await cb.answer()


###############################################################################
# Удалить пользователя из группы (админ группы)
###############################################################################
@router.message(lambda msg: msg.text in {"Удалить пользователя из группы", "Удалить из группы"} and not is_superadmin(msg.from_user.id))
async def remove_user_prompt(message: types.Message):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS)
        return
    if not group_id:
        await message.answer("Для удаления сотрудника выберите рабочую группу (кнопка «Сменить группу»).")
        return

    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы удаляете пользователя из группы.\nЕсли передумали, нажмите «Отмена».",
        reply_markup=cancel_kb
    )

    members = get_group_members(group_id)
    if not members:
        await message.answer(TEXT_GROUP_NO_USERS)
        return

    kb_rows = []
    for (tid, fname, username, role) in members:
        role_label = _group_role_label(role)
        label = f"{fname}"
        if username:
            label += f" (@{username})"
        label += f" [{role_label}]"
        kb_rows.append([
            InlineKeyboardButton(text=label, callback_data=f"remove_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите пользователя для удаления:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("remove_user:"))
async def callback_remove_user(cb: CallbackQuery):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if not group_id:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    user_id = int(cb.data.split(":")[1])
    if not user_in_group(user_id, group_id):
        await cb.answer(TEXT_USER_NOT_IN_GROUP, show_alert=True)
        return

    remove_user_from_group(user_id, group_id)

    group_name = get_group_name(group_id) or f"ID={group_id}"
    await cb.message.answer(f"Пользователь {user_id} удалён из группы {group_name}.")
    log_action(admin_id, f"remove_user_from_group {user_id} group={group_id}")
    try:
        await bot.send_message(
            user_id,
            f"Вы удалены из группы {group_name}.",
            reply_markup=get_role_menu(user_id)
        )
    except Exception:
        pass
    await cb.answer()


###############################################################################
# Мои группы / заявки в группу
###############################################################################
@router.message(lambda msg: msg.text == "Мои группы")
async def show_my_groups(message: types.Message):
    user_id = message.from_user.id
    if not user_exists_in_db(user_id):
        await message.answer(TEXT_NOT_REGISTERED_SHORT)
        return

    groups = get_user_groups(user_id)
    if not groups:
        await message.answer(TEXT_NO_GROUPS_YET)
        return

    lines = []
    for gid, name, role in groups:
        role_label = _group_role_label(role)
        lines.append(f"- {name} (ID={gid}, роль: {role_label})")

    await message.answer("Ваши группы:\n" + "\n".join(lines))


@router.message(lambda msg: msg.text == "Запросить роль наблюдателя")
async def request_viewer_role_start(message: types.Message):
    user_id = message.from_user.id
    if not user_exists_in_db(user_id):
        await message.answer(TEXT_NOT_REGISTERED_SHORT)
        return
    if not is_user_approved(user_id):
        await message.answer(TEXT_NOT_APPROVED_SHORT)
        return

    member_groups = [(gid, name) for gid, name, role in get_user_groups(user_id) if role == "member"]
    if not member_groups:
        await message.answer("Нет групп, где можно запросить роль наблюдателя.")
        return

    kb_rows = []
    for gid, name in member_groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"req_viewer:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите группу для запроса роли наблюдателя:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("req_viewer:"))
async def request_viewer_role(cb: CallbackQuery):
    user_id = cb.from_user.id
    if not is_user_approved(user_id):
        await cb.answer(TEXT_NOT_APPROVED_SHORT, show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    role = get_group_membership_role(user_id, group_id)
    if role != "member":
        await cb.answer("Запрос роли доступен только участнику группы.", show_alert=True)
        return

    if has_pending_group_role_request(user_id, group_id, "viewer"):
        await cb.answer(TEXT_REQUEST_ALREADY_PENDING, show_alert=True)
        return

    req_id = create_group_role_request(user_id, group_id, "viewer", user_id)
    await cb.message.answer(
        f"Заявка #{req_id} на роль наблюдателя для группы «{group_name}» отправлена."
    )
    await cb.answer()
    log_action(user_id, f"group_role_request create #{req_id} viewer group={group_id}")

    recipients = set(get_admins())
    recipients.update(get_group_admins(group_id))
    user_display = get_user_fullname(user_id)
    for admin_id in recipients:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Одобрить", callback_data=f"grp_role_approve:{req_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"grp_role_decline:{req_id}")
        ]])
        text = (
            f"{user_display} запросил роль наблюдателя.\n"
            f"Группа: {group_name} (ID={group_id})\n"
            f"Заявка #{req_id}"
        )
        try:
            await bot.send_message(admin_id, text, reply_markup=kb)
        except Exception:
            pass


@router.message(lambda msg: msg.text == "Запроситься в группу")
async def request_join_group_start(message: types.Message):
    user_id = message.from_user.id
    if not user_exists_in_db(user_id):
        await message.answer(TEXT_NOT_REGISTERED_SHORT)
        return
    if not is_user_approved(user_id):
        await message.answer(TEXT_NOT_APPROVED_SHORT)
        return

    groups = list_all_groups()
    if not groups:
        await message.answer("Группы пока не созданы.")
        return

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"join_group:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите группу для вступления:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("join_group:"))
async def request_join_group(cb: CallbackQuery):
    user_id = cb.from_user.id
    if not is_user_approved(user_id):
        await cb.answer(TEXT_NOT_APPROVED_SHORT, show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    if user_in_group(user_id, group_id):
        await cb.answer("Вы уже состоите в этой группе.", show_alert=True)
        return

    if has_pending_group_request(user_id, group_id, "join"):
        await cb.answer(TEXT_REQUEST_ALREADY_PENDING, show_alert=True)
        return

    req_id = create_group_request(user_id, group_id, "join", user_id)

    await cb.message.answer(f"Заявка на вступление в группу «{group_name}» отправлена.")
    await cb.answer()

    # Уведомим админов группы и суперадминов
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Одобрить", callback_data=f"grp_req_approve:{req_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"grp_req_decline:{req_id}")
    ]])
    text_admin = (
        f"Запрос на вступление в группу «{group_name}»\n"
        f"От: {get_user_fullname(user_id)}"
    )
    admin_ids = set(get_group_admins(group_id) + get_admins())
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text_admin, reply_markup=kb)
        except Exception:
            pass


@router.message(lambda msg: msg.text == "Выйти из группы")
async def request_leave_group_start(message: types.Message):
    user_id = message.from_user.id
    if not user_exists_in_db(user_id):
        await message.answer(TEXT_NOT_REGISTERED_SHORT)
        return
    if not is_user_approved(user_id):
        await message.answer(TEXT_NOT_APPROVED_SHORT)
        return

    groups = get_user_groups(user_id)
    if not groups:
        await message.answer(TEXT_NO_GROUPS_YET)
        return

    kb_rows = []
    for gid, name, _role in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"leave_group:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите группу для выхода:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("leave_group:"))
async def request_leave_group(cb: CallbackQuery):
    user_id = cb.from_user.id
    if not is_user_approved(user_id):
        await cb.answer(TEXT_NOT_APPROVED_SHORT, show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    if not user_in_group(user_id, group_id):
        await cb.answer("Вы не состоите в этой группе.", show_alert=True)
        return

    if has_pending_group_request(user_id, group_id, "leave"):
        await cb.answer(TEXT_REQUEST_ALREADY_PENDING, show_alert=True)
        return

    req_id = create_group_request(user_id, group_id, "leave", user_id)

    await cb.message.answer(f"Заявка на выход из группы «{group_name}» отправлена.")
    await cb.answer()

    # Уведомим админов группы и суперадминов
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Одобрить", callback_data=f"grp_req_approve:{req_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"grp_req_decline:{req_id}")
    ]])
    text_admin = (
        f"Запрос на выход из группы «{group_name}»\n"
        f"От: {get_user_fullname(user_id)}"
    )
    admin_ids = set(get_group_admins(group_id) + get_admins())
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text_admin, reply_markup=kb)
        except Exception:
            pass
