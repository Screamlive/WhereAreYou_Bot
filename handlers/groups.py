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
    user_is_group_admin_any,
    get_admin_scope,
    get_admin_groups,
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
    remove_user_from_group,
    list_pending_group_requests,
    get_group_request,
    set_group_request_status,
    create_group_request,
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
    TEXT_WORK_GROUP_RESET_GLOBAL,
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


def set_bot(bot_instance: Bot) -> None:
    global bot
    bot = bot_instance


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
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
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
        role_label = "админ" if role == "admin" else "участник"
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
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"gm_user:{uid}")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)
    await state.set_state(GroupAddUserFSM.waiting_for_user)
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("gm_user:"), GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_pick_user(cb: CallbackQuery, state: FSMContext):
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
            msg = "Пользователь уже состоит в группе."
    else:
        add_group_membership(user_id, group_id, "member", cb.from_user.id)
        msg = "Пользователь добавлен в группу."
        try:
            group_name = get_group_name(group_id) or f"ID={group_id}"
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

    await cb.message.answer(msg, reply_markup=get_role_menu(cb.from_user.id))
    await cb.answer()
    await state.clear()


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
        role_label = "админ" if role == "admin" else "участник"
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
    if not is_superadmin(user_id) and not user_is_group_admin_any(user_id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    group_id = None
    if not is_superadmin(user_id):
        group_id = get_last_group_id(user_id)
        if not group_id:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
            return
        if not is_group_admin(user_id, group_id):
            await message.answer(TEXT_NO_RIGHTS)
            return
    else:
        group_id = get_last_group_id(user_id)

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
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Одобрить", callback_data=f"grp_req_approve:{req_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"grp_req_decline:{req_id}")
        ]])
        await message.answer(text, reply_markup=kb)


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


###############################################################################
# Сменить рабочую группу (админ/суперадмин)
###############################################################################
@router.message(lambda msg: msg.text == "Сменить группу")
async def change_work_group(message: types.Message):
    user_id = message.from_user.id

    admin_groups = get_admin_groups(user_id)

    if not is_superadmin(user_id) and not admin_groups:
        await message.answer(TEXT_NO_RIGHTS)
        return

    if is_superadmin(user_id):
        groups = list_all_groups()
        allow_global = True
    else:
        groups = [(gid, name) for (gid, name) in admin_groups]
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
    await message.answer(TEXT_WORK_GROUP_RESET_GLOBAL, reply_markup=get_role_menu(message.from_user.id))


@router.message(lambda msg: msg.text == "Выбрать группу")
async def select_work_group_alias(message: types.Message):
    await change_work_group(message)


@router.callback_query(lambda c: c.data.startswith("set_group:"))
async def set_work_group(cb: CallbackQuery):
    user_id = cb.from_user.id
    payload = cb.data.split(":", 1)[1]

    if payload == "global":
        if not is_superadmin(user_id):
            await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
            return
        set_last_group_id(user_id, None)
        await cb.message.answer(TEXT_WORK_GROUP_RESET_GLOBAL)
        await cb.answer()
        return

    try:
        group_id = int(payload)
    except ValueError:
        await cb.answer(TEXT_INVALID_GROUP, show_alert=True)
        return

    if not is_superadmin(user_id) and not is_group_admin(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer(TEXT_GROUP_NOT_FOUND, show_alert=True)
        return

    if not set_last_group_id(user_id, group_id):
        await cb.answer("Пользователь не найден.", show_alert=True)
        return

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
        role_label = "админ" if role == "admin" else "участник"
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
        role_label = "админ" if role == "admin" else "участник"
        lines.append(f"- {name} (ID={gid}, роль: {role_label})")

    await message.answer("Ваши группы:\n" + "\n".join(lines))


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
