from aiogram import Bot, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from core import get_admin_scope, get_group_scope, get_role_menu, is_superadmin
from db_repo import (
    log_action,
    user_exists_in_db,
    is_user_admin,
    get_admins,
    get_approved_users,
    get_group_members,
    get_all_users,
    get_user_fullname,
    upsert_user_registration,
    get_user_approval_status,
    approve_user,
    delete_user_and_related,
    list_pending_user_ids,
    list_non_admin_approved_users,
    list_admin_users,
    promote_to_admin,
    revoke_admin,
    update_user_fullname,
    get_user_name_and_username,
)
from texts import (
    TEXT_EMPTY_VALUE,
    TEXT_NO_RIGHTS_ADMIN_ALERT,
    TEXT_USER_NOT_FOUND,
    TEXT_REQUEST_APPROVED,
    TEXT_NO_RIGHTS,
    TEXT_NO_RIGHTS_ADMIN,
    TEXT_SELECT_GROUP_FIRST,
    TEXT_CANCEL_BUTTON,
    TEXT_CANCEL_HINT,
    TEXT_NO_APPROVED_EMPLOYEES,
    TEXT_GROUP_NO_USERS,
    TEXT_SELECT_USER,
    TEXT_INVALID_USER,
    TEXT_NOT_REGISTERED_SHORT,
    TEXT_USERS_NOT_FOUND,
)

router = Router()
bot: Bot | None = None


def set_bot(bot_instance: Bot) -> None:
    global bot
    bot = bot_instance


###############################################################################
# FSM для запроса ФИО при регистрации
###############################################################################
class RegistrationFSM(StatesGroup):
    waiting_for_fullname = State()


@router.message(lambda msg: msg.text == "Зарегистрироваться")
async def register_via_button(message: types.Message, state: FSMContext):
    """
    Начинаем процедуру запроса ФИО.
    """
    await message.answer("Введите ваши Фамилию и инициалы (пример: Иванов И. И.):")
    await state.set_state(RegistrationFSM.waiting_for_fullname)


@router.message(RegistrationFSM.waiting_for_fullname)
async def process_fullname(message: types.Message, state: FSMContext):
    fullname = message.text.strip()
    if not fullname:
        await message.answer(TEXT_EMPTY_VALUE)
        return

    tg_id = message.from_user.id
    username = message.from_user.username or ""
    log_action(tg_id, f"Регистрация. Указал ФИО: {fullname}")

    upsert_user_registration(tg_id, username, fullname)

    await message.answer("Спасибо! Ваша заявка отправлена администратору.")
    await state.clear()

    # Уведомляем админов
    admins = get_admins()
    if not admins:
        await message.answer("Админов в системе нет.")
        return

    # inline-кнопки
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Одобрить", callback_data=f"approve_user:{tg_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"decline_user:{tg_id}")
    ]])

    fstring = get_user_fullname(tg_id)
    for admin_id in admins:
        try:
            await bot.send_message(admin_id, f"Новая заявка от {fstring}.", reply_markup=kb)
        except Exception:
            pass


###############################################################################
# Инлайн обработка approve_user / decline_user
###############################################################################
@router.callback_query(lambda c: c.data.startswith("approve_user:") or c.data.startswith("decline_user:"))
async def inline_approve_user(cb: CallbackQuery):
    if not is_user_admin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ADMIN_ALERT, show_alert=True)
        return

    action, user_id_str = cb.data.split(":")
    user_id = int(user_id_str)

    status = get_user_approval_status(user_id)
    if status is None:
        await cb.answer(TEXT_USER_NOT_FOUND, show_alert=True)
        return

    if action == "approve_user":
        if status == 1:
            await cb.answer("Этот пользователь уже одобрен.", show_alert=True)
            return
        approve_user(user_id)

        fname = get_user_fullname(user_id)
        await cb.message.answer(f"{fname} — теперь одобрен.")
        log_action(cb.from_user.id, f"approve_user {user_id}")
        await cb.answer()

        try:
            await bot.send_message(user_id, TEXT_REQUEST_APPROVED, reply_markup=get_role_menu(user_id))
        except Exception:
            pass

    else:  # decline_user
        if status == 1:
            await cb.answer("Этот пользователь уже одобрен, отклонение не имеет смысла.", show_alert=True)
            return
        delete_user_and_related(user_id)

        await cb.message.answer(f"Пользователь {user_id} удалён и отклонён.")
        log_action(cb.from_user.id, f"decline_user {user_id}")
        await cb.answer()

        try:
            await bot.send_message(user_id, "Ваш запрос отклонён и вы удалены.")
        except Exception:
            pass


###############################################################################
# Команды /approve <id>, /decline <id> (дополнительно)
###############################################################################
@router.message(Command("approve"))
async def cmd_approve(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    # Cancel KB
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        f"Сейчас вы удаляете сотрудника.\n{TEXT_CANCEL_HINT}",
        reply_markup=cancel_kb
    )

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Используйте: /approve <telegram_id>")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("Неверный формат.")
        return

    approve_user(target_id)

    await message.answer(f"Пользователь {target_id} одобрен.")
    log_action(message.from_user.id, f"approve {target_id}")
    try:
        await bot.send_message(target_id, TEXT_REQUEST_APPROVED, reply_markup=get_role_menu(target_id))
    except Exception:
        pass


@router.message(Command("decline"))
async def cmd_decline(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Используйте: /decline <telegram_id>")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("Неверный формат.")
        return

    delete_user_and_related(target_id)
    await message.answer(f"Пользователь {target_id} удалён (decline).")
    log_action(message.from_user.id, f"decline {target_id}")
    try:
        await bot.send_message(target_id, "Ваш запрос отклонён, вы удалены.")
    except Exception:
        pass


###############################################################################
# "Список запросов" (неодобренных), "Список пользователей"
###############################################################################
@router.message(lambda msg: msg.text in {"Список запросов", "Список запросов (регистрация)", "Заявки регистрации"})
async def list_pending_users(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    rows = list_pending_user_ids()
    if not rows:
        await message.answer("Нет заявок на одобрение.")
        return

    text_list = "Ожидают одобрения:\n"
    kb_rows = []
    for tid in rows:
        disp = get_user_fullname(tid)
        text_list += f"- {disp}\n"
        kb_rows.append([InlineKeyboardButton(text=disp, callback_data=f"dummy:{tid}")])
        kb_rows.append([
            InlineKeyboardButton(text="Одобрить", callback_data=f"approve_user:{tid}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"decline_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(text_list, reply_markup=inline_kb)


@router.message(lambda msg: msg.text in {"Список сотрудников", "Список пользователей"})
async def list_approved_users(message: types.Message):
    tg_id = message.from_user.id
    can_read, _can_write, group_id, need_select = get_group_scope(tg_id)
    if not can_read:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS)
        return

    if group_id:
        members = get_group_members(group_id)
        if not members:
            await message.answer(TEXT_GROUP_NO_USERS)
            return
        text_list = "Сотрудники группы:\n"
        for uid, fullname, username, role in members:
            role_label = "админ" if role == "admin" else ("наблюдатель" if role == "viewer" else "участник")
            uname = f" (@{username})" if username else ""
            text_list += f"- {fullname}{uname} (ID={uid}, {role_label})\n"
        await message.answer(text_list)
        return

    # Глобально (суперадмин)
    rows = get_approved_users()

    if not rows:
        await message.answer(TEXT_NO_APPROVED_EMPLOYEES)
        return

    text_list = "Одобренные сотрудники:\n"
    for (uid, fname, username) in rows:
        uname = f" (@{username})" if username else ""
        text_list += f"- {fname}{uname} (ID={uid})\n"
    await message.answer(text_list)


###############################################################################
# Суперадмин: изменить имя пользователя / показать @username
###############################################################################
class SuperadminChangeNameFSM(StatesGroup):
    waiting_for_user = State()
    waiting_for_fullname = State()


class SuperadminShowUsernameFSM(StatesGroup):
    waiting_for_user = State()


@router.message(lambda msg: msg.text in {"Изменить имя пользователя", "Изменить ФИО"})
async def superadmin_change_name_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    users = get_all_users()
    if not users:
        await message.answer(TEXT_USERS_NOT_FOUND)
        return

    await state.clear()
    kb_rows = []
    for uid, fullname, username in users:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"sa_name_user:{uid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)
    await state.set_state(SuperadminChangeNameFSM.waiting_for_user)


@router.callback_query(lambda c: c.data.startswith("sa_name_user:"), SuperadminChangeNameFSM.waiting_for_user)
async def superadmin_change_name_pick_user(cb: CallbackQuery, state: FSMContext):
    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    await state.update_data(user_id=user_id)
    await cb.message.answer("Введите новое имя (ФИО):")
    await state.set_state(SuperadminChangeNameFSM.waiting_for_fullname)
    await cb.answer()


@router.message(SuperadminChangeNameFSM.waiting_for_fullname)
async def superadmin_change_name_finish(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.answer(TEXT_EMPTY_VALUE)
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Пользователь не выбран.")
        await state.clear()
        return

    updated = update_user_fullname(user_id, new_name)
    if not updated:
        await message.answer(TEXT_USER_NOT_FOUND)
        await state.clear()
        return

    await message.answer(f"Имя пользователя обновлено: {new_name}", reply_markup=get_role_menu(message.from_user.id))
    try:
        await bot.send_message(user_id, f"Ваше имя обновлено суперадминистратором: {new_name}")
    except Exception:
        pass
    log_action(message.from_user.id, f"superadmin_change_name {user_id}")
    await state.clear()


@router.message(lambda msg: msg.text == "Показать @username")
async def superadmin_show_username_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    users = get_all_users()
    if not users:
        await message.answer(TEXT_USERS_NOT_FOUND)
        return

    await state.clear()
    kb_rows = []
    for uid, fullname, username in users:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"sa_uname_user:{uid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)
    await state.set_state(SuperadminShowUsernameFSM.waiting_for_user)


@router.callback_query(lambda c: c.data.startswith("sa_uname_user:"), SuperadminShowUsernameFSM.waiting_for_user)
async def superadmin_show_username_pick_user(cb: CallbackQuery, state: FSMContext):
    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    row = get_user_name_and_username(user_id)
    if not row:
        await cb.answer(TEXT_USER_NOT_FOUND, show_alert=True)
        await state.clear()
        return

    fullname, username = row
    uname = f"@{username}" if username else "не указан"
    label = fullname or f"User {user_id}"
    await cb.message.answer(f"{label}: {uname}")
    await cb.answer()
    await state.clear()


###############################################################################
# Суперадмин: удалить пользователя из бота
###############################################################################
@router.message(lambda msg: msg.text in {"Удалить пользователя из бота", "Удалить из бота"})
async def superadmin_delete_user_start(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    users = get_all_users()
    if not users:
        await message.answer(TEXT_USERS_NOT_FOUND)
        return

    kb_rows = []
    for uid, fullname, username in users:
        label = fullname or f"User {uid}"
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"del_bot_user:{uid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите пользователя для удаления:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("del_bot_user:"))
async def superadmin_delete_user_confirm(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ADMIN_ALERT, show_alert=True)
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    if user_id == cb.from_user.id:
        await cb.answer("Нельзя удалить самого себя.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Удалить пользователя", callback_data=f"del_bot_user_confirm:{user_id}"),
        InlineKeyboardButton(text="Отмена", callback_data="del_bot_user_cancel")
    ]])
    await cb.message.answer(
        f"Подтвердите удаление пользователя {get_user_fullname(user_id)}.",
        reply_markup=kb
    )
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("del_bot_user_confirm:"))
async def superadmin_delete_user_confirmed(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ADMIN_ALERT, show_alert=True)
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    if user_id == cb.from_user.id:
        await cb.answer("Нельзя удалить самого себя.", show_alert=True)
        return

    fullname = get_user_fullname(user_id)
    delete_user_and_related(user_id)

    log_action(cb.from_user.id, f"delete_user_from_bot {user_id}")
    await cb.message.answer(f"Пользователь удалён из бота: {fullname}", reply_markup=get_role_menu(cb.from_user.id))
    try:
        await bot.send_message(user_id, "Ваш аккаунт удалён из бота администратором.")
    except Exception:
        pass
    await cb.answer()


@router.callback_query(lambda c: c.data == "del_bot_user_cancel")
async def superadmin_delete_user_cancel(cb: CallbackQuery):
    await cb.message.answer("Удаление пользователя отменено.")
    await cb.answer()


###############################################################################
# Назначить админом /make_admin, Отозвать админа /revoke_admin, Список админов
###############################################################################
@router.message(lambda msg: msg.text in {"Назначить админом", "Добавить права суперадминистратора", "Сделать суперадмином"})
async def pick_user_for_admin(message: types.Message):
    """
    Шаг 1: админ нажимает "Назначить админом".
    Бот показывает список одобренных, но не админов (is_approved=1, is_admin=0).
    """
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    rows = list_non_admin_approved_users()
    if not rows:
        await message.answer("Нет подходящих пользователей (либо все уже админы).")
        return

    kb_rows = []
    for (tid, fname) in rows:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"make_admin_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите пользователя для назначения администратором:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("make_admin_user:"))
async def callback_make_admin_user(cb: CallbackQuery):
    """
    Шаг 2: админ выбрал конкретного пользователя — делаем его админом.
    """
    if not is_user_admin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ADMIN_ALERT, show_alert=True)
        return

    user_id_str = cb.data.split(":")[1]
    user_id = int(user_id_str)

    promote_to_admin(user_id)

    await cb.message.answer(f"Пользователь {get_user_fullname(user_id)} теперь администратор.")
    log_action(cb.from_user.id, f"make_admin {user_id}")

    # Уведомим
    try:
        await bot.send_message(user_id, "Вам назначены права администратора!", reply_markup=get_role_menu(user_id))
    except Exception:
        pass

    await cb.answer()


@router.message(lambda msg: msg.text in {"Отозвать админа", "Отозвать права суперадминистратора", "Снять суперадмина"})
async def pick_admin_to_revoke(message: types.Message):
    """
    Шаг 1: админ нажимает "Отозвать админа".
    Бот показывает список пользователей, у которых is_admin=1 (кроме себя, если хотите).
    """
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    rows = list_admin_users(exclude_id=message.from_user.id)
    if not rows:
        await message.answer("Нет других администраторов, которым можно отозвать права.")
        return

    kb_rows = []
    for (tid, fname) in rows:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"revoke_admin_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите админа, у которого хотите отозвать права:", reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("revoke_admin_user:"))
async def callback_revoke_admin_user(cb: CallbackQuery):
    """
    Шаг 2: выбран конкретный админ, у которого отзываем права.
    """
    if not is_user_admin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ADMIN_ALERT, show_alert=True)
        return

    user_id_str = cb.data.split(":")[1]
    user_id = int(user_id_str)

    revoke_admin(user_id)

    await cb.message.answer(f"Админ-права у {get_user_fullname(user_id)} отозваны.")
    log_action(cb.from_user.id, f"revoke_admin {user_id}")

    try:
        await bot.send_message(
            user_id,
            "У вас отозвали права администратора.",
            reply_markup=get_role_menu(user_id)
        )
    except Exception:
        pass

    await cb.answer()


@router.message(lambda msg: msg.text in {"Список админов", "Список суперадминистраторов", "Список суперадминов"})
async def list_admins_cmd(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    rows = get_admins()
    if not rows:
        await message.answer("Нет суперадминистраторов.")
        return

    txt = "Список суперадминистраторов:\n"
    for tid in rows:
        txt += f"- {get_user_fullname(tid)}\n"
    await message.answer(txt)


###############################################################################
# Обновить меню
###############################################################################
async def broadcast_new_menu():
    """
    Рассылает новое меню всем одобренным пользователям.
    """
    rows = get_approved_users()

    updated_count = 0
    for (tg_id, _fullname, _username) in rows:
        try:
            await bot.send_message(
                tg_id,
                "Бот обновлён! Вот ваше меню:",
                reply_markup=get_role_menu(tg_id)
            )
            updated_count += 1
        except Exception:
            pass


# Команда /refresh_menu, чтобы запустить эту рассылку вручную
@router.message(Command("refresh_menu"))
async def cmd_refresh_menu(message: types.Message):
    # Проверим права админа, чтобы только админ мог перезапускать обновление
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    await broadcast_new_menu()
    await message.answer("Меню обновлено у всех одобренных пользователей.")
