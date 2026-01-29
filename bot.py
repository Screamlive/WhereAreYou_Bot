import asyncio
import logging
import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import StatesGroup, State

# Предполагаем, что в config.py лежат TOKEN, DB_NAME
from config import TOKEN, DB_NAME
from database import init_db  # Создаёт таблицы, если нет
from db_repo import (
    log_action,
    user_exists_in_db,
    is_user_approved,
    is_user_admin,
    get_admins,
    get_last_group_id,
    set_last_group_id,
    list_all_groups,
    get_group_name,
    get_user_groups,
    user_in_group,
    has_pending_group_request,
    is_group_admin,
    get_group_admins,
    get_approved_users,
    get_group_members,
    get_all_users,
    get_user_fullname,
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
    create_absence,
    list_user_absences,
    get_absence_by_id,
    update_absence,
    update_absence_status,
    delete_absence,
    list_pending_absences,
    create_edit_request,
    get_edit_request,
    delete_edit_request,
    list_approved_absences_between,
    list_approved_absences_for_date,
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
from keyboards import (
    BACK_BUTTON_TEXT,
    not_approved_menu,
    superadmin_main_menu,
    group_admin_main_menu,
    user_main_menu,
    no_group_menu,
    group_admin_select_menu,
    my_absences_menu,
    superadmin_users_menu,
    superadmin_groups_menu,
    superadmin_absences_menu,
    superadmin_superadmins_menu,
    superadmin_work_group_menu,
    group_admin_requests_menu,
    group_admin_users_menu,
    group_admin_absences_menu,
    group_admin_groups_menu,
    group_admin_groups_menu_single,
    user_groups_menu,
    no_group_groups_menu,
    user_other_absences_menu,
)
from utils import format_date_display
from texts import (
    TEXT_NO_RIGHTS,
    TEXT_NO_RIGHTS_ALERT,
    TEXT_NO_RIGHTS_ADMIN,
    TEXT_NO_RIGHTS_ADMIN_ALERT,
    TEXT_SELECT_GROUP_FIRST,
    TEXT_SELECT_GROUP_FIRST_ALERT,
    TEXT_NOT_REGISTERED,
    TEXT_NOT_APPROVED,
    TEXT_CANCELLED,
    TEXT_BACK_TO_MENU,
    TEXT_UNKNOWN_COMMAND,
    TEXT_CANCEL_BUTTON,
    TEXT_CANCEL_HINT,
    TEXT_CANCEL_HINT_GENERIC,
    TEXT_SELECT_USER,
    TEXT_SELECT_GROUP,
    TEXT_GROUPS_NOT_FOUND,
    TEXT_USERS_NOT_FOUND,
    TEXT_NO_APPROVED_USERS,
    TEXT_NO_APPROVED_EMPLOYEES,
    TEXT_GROUP_NO_USERS,
    TEXT_GROUP_NOT_FOUND,
    TEXT_GROUP_NOT_SELECTED,
    TEXT_INVALID_GROUP,
    TEXT_INVALID_USER,
    TEXT_USER_NOT_FOUND,
    TEXT_REQUEST_NOT_FOUND,
    TEXT_ORIGINAL_REQUEST_NOT_FOUND,
    TEXT_EMPTY_VALUE,
    TEXT_REQUEST_APPROVED,
    TEXT_END_DATE_BEFORE_START,
    TEXT_INVALID_DATE_FORMAT,
    TEXT_INVALID_DATE_TRY_AGAIN,
    TEXT_ENTER_END_DATE,
    TEXT_ENTER_NEW_START_DATE,
    TEXT_ENTER_NEW_END_DATE,
    TEXT_ENTER_COMMENT,
    TEXT_ENTER_NEW_COMMENT,
    TEXT_SELECT_ABSENCE_CATEGORY,
    TEXT_NO_GROUPS_YET,
    TEXT_NOT_IN_ANY_GROUP,
    TEXT_REQUEST_ALREADY_PENDING,
    TEXT_NOT_YOUR_REQUEST,
    TEXT_CANNOT_DELETE_SELF,
    TEXT_USER_ALREADY_GROUP_ADMIN,
    TEXT_USER_NOT_IN_GROUP,
    TEXT_WORK_GROUP_RESET_GLOBAL,
    TEXT_MENU_UPDATED,
    TEXT_INVALID_REQUEST,
    TEXT_NOT_APPROVED_SHORT,
    TEXT_NOT_REGISTERED_SHORT,
    TEXT_NOT_REGISTERED_LONG,
    TEXT_ENTER_PERIOD_START_OR_CANCEL,
    TEXT_ENTER_PERIOD_END_OR_CANCEL,
    TEXT_SECTION_GROUPS,
)

###############################################################################
# ЛОГИРОВАНИЕ
###############################################################################
logging.basicConfig(level=logging.DEBUG)

###############################################################################
# ИНИЦИАЛИЗАЦИЯ БД И БОТА
###############################################################################
init_db()  # создание таблиц, если нет
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

###############################################################################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (ЛОГИКА)
###############################################################################
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

###############################################################################
# НАВИГАЦИЯ ПО МЕНЮ
###############################################################################
@dp.message(lambda msg: msg.text == "Мои отсутствия")
async def open_my_absences_menu(message: types.Message):
    await message.answer("Раздел «Мои отсутствия». Выберите действие:", reply_markup=my_absences_menu)

@dp.message(lambda msg: msg.text == "Управление пользователями")
async def open_superadmin_users_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Управление пользователями».", reply_markup=superadmin_users_menu)

@dp.message(lambda msg: msg.text == "Управление группами")
async def open_superadmin_groups_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Управление группами».", reply_markup=superadmin_groups_menu)

@dp.message(lambda msg: msg.text == "Управление отсутствиями")
async def open_superadmin_absences_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Управление отсутствиями».", reply_markup=superadmin_absences_menu)

@dp.message(lambda msg: msg.text == "Управление суперадминами")
async def open_superadmin_admins_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Управление суперадминами».", reply_markup=superadmin_superadmins_menu)

@dp.message(lambda msg: msg.text == "Рабочая группа")
async def open_superadmin_work_group_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Рабочая группа».", reply_markup=superadmin_work_group_menu)

@dp.message(lambda msg: msg.text == "Заявки в группу")
async def open_group_requests_menu(message: types.Message):
    if not is_superadmin(message.from_user.id) and not user_is_group_admin_any(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Заявки в группу».", reply_markup=group_admin_requests_menu)

@dp.message(lambda msg: msg.text == "Пользователи группы")
async def open_group_users_menu(message: types.Message):
    if not is_superadmin(message.from_user.id) and not user_is_group_admin_any(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Пользователи группы».", reply_markup=group_admin_users_menu)

@dp.message(lambda msg: msg.text == "Управление отсутствиями группы")
async def open_group_absences_menu(message: types.Message):
    if not is_superadmin(message.from_user.id) and not user_is_group_admin_any(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer("Раздел «Управление отсутствиями группы».", reply_markup=group_admin_absences_menu)

@dp.message(lambda msg: msg.text == "Группы")
async def open_groups_menu(message: types.Message):
    tg_id = message.from_user.id
    if is_superadmin(tg_id):
        await message.answer("Используйте раздел «Управление группами».")
        return
    if not user_has_any_group(tg_id):
        await message.answer(TEXT_SECTION_GROUPS, reply_markup=no_group_groups_menu)
        return
    if user_is_group_admin_any(tg_id):
        admin_groups = get_admin_groups(tg_id)
        if len(admin_groups) == 1:
            await message.answer(TEXT_SECTION_GROUPS, reply_markup=group_admin_groups_menu_single)
        else:
            await message.answer(TEXT_SECTION_GROUPS, reply_markup=group_admin_groups_menu)
        return
    await message.answer(TEXT_SECTION_GROUPS, reply_markup=user_groups_menu)

@dp.message(lambda msg: msg.text == "Отсутствия для другого пользователя")
async def open_other_absences_menu(message: types.Message):
    if not is_user_approved(message.from_user.id):
        await message.answer(TEXT_NOT_APPROVED_SHORT)
        return
    await message.answer("Раздел «Отсутствия для другого пользователя».", reply_markup=user_other_absences_menu)


@dp.message(lambda msg: msg.text == "Текущая группа")
async def show_current_group(message: types.Message):
    user_id = message.from_user.id
    if is_superadmin(user_id):
        group_id = get_last_group_id(user_id)
        if group_id:
            name = get_group_name(group_id) or f"ID={group_id}"
            await message.answer(f"Текущая группа: {name}")
        else:
            await message.answer("Текущая группа: глобально")
        return

    if not user_is_group_admin_any(user_id):
        await message.answer("У вас нет прав администратора группы.")
        return

    group_id = get_last_group_id(user_id)
    if not group_id:
        await message.answer("Группа не выбрана. Нажмите «Сменить группу».")
        return

    name = get_group_name(group_id) or f"ID={group_id}"
    await message.answer(f"Текущая группа: {name}")

###############################################################################
# /start
###############################################################################
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    tg_id = message.from_user.id

    if not user_exists_in_db(tg_id):
        await message.answer(
            TEXT_NOT_REGISTERED_LONG,
            reply_markup=not_approved_menu
        )
        return

    if not is_user_approved(tg_id):
        await message.answer(
            "Ваш аккаунт ещё не одобрен администратором. "
            "Нажмите «Зарегистрироваться» при необходимости повторить.",
            reply_markup=not_approved_menu
        )
        return

    # Если пользователь одобрен
    if not is_superadmin(tg_id) and not user_has_any_group(tg_id):
        await message.answer(
            "Вы пока не состоите ни в одной группе. "
            "Откройте раздел «Группы» и подайте заявку на вступление.",
            reply_markup=no_group_menu
        )
        return

    if is_superadmin(tg_id):
        await message.answer("Здравствуйте, Суперадминистратор!", reply_markup=superadmin_main_menu)
        return

    admin_groups = get_admin_groups(tg_id)
    if admin_groups:
        if len(admin_groups) == 1:
            only_gid, only_name = admin_groups[0]
            set_last_group_id(tg_id, only_gid)
            await message.answer(
                f"Здравствуйте, Администратор группы! Рабочая группа: {only_name}",
                reply_markup=group_admin_main_menu
            )
            return

        if get_last_group_id(tg_id):
            gname = get_group_name(get_last_group_id(tg_id)) or "выбрана"
            await message.answer(
                f"Здравствуйте, Администратор группы! Рабочая группа: {gname}",
                reply_markup=group_admin_main_menu
            )
            return

        # несколько групп и нет выбранной — просим выбрать
        kb_rows = []
        for gid, name in admin_groups:
            kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"set_group:{gid}")])
        inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await message.answer(
            "Здравствуйте, Администратор группы! Выберите рабочую группу:",
            reply_markup=inline_kb
        )
        await message.answer(
            "После выбора появится меню управления группой.",
            reply_markup=group_admin_select_menu
        )
        return

    await message.answer("Добро пожаловать, Пользователь!", reply_markup=get_role_menu(tg_id))

###############################################################################
# FSM для запроса ФИО при регистрации
###############################################################################
class RegistrationFSM(StatesGroup):
    waiting_for_fullname = State()

@dp.message(lambda msg: msg.text == "Зарегистрироваться")
async def register_via_button(message: types.Message, state: FSMContext):
    """
    Начинаем процедуру запроса ФИО.
    """
    # Если пользователь уже есть, но не одобрен — обновим fullname.
    await message.answer("Введите ваши Фамилию и инициалы (пример: Иванов И. И.):")
    await state.set_state(RegistrationFSM.waiting_for_fullname)

@dp.message(RegistrationFSM.waiting_for_fullname)
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
        except:
            pass

###############################################################################
# Инлайн обработка approve_user / decline_user
###############################################################################
@dp.callback_query(lambda c: c.data.startswith("approve_user:") or c.data.startswith("decline_user:"))
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
            if is_user_admin(user_id):
                await bot.send_message(user_id, TEXT_REQUEST_APPROVED, reply_markup=get_role_menu(user_id))
            else:
                await bot.send_message(user_id, TEXT_REQUEST_APPROVED, reply_markup=get_role_menu(user_id))
        except:
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
        except:
            pass

###############################################################################
# Команды /approve <id>, /decline <id> (дополнительно)
###############################################################################
@dp.message(Command("approve"))
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
        if is_user_admin(target_id):
            await bot.send_message(target_id, TEXT_REQUEST_APPROVED, reply_markup=get_role_menu(target_id))
        else:
            await bot.send_message(target_id, TEXT_REQUEST_APPROVED, reply_markup=get_role_menu(target_id))
    except:
        pass

@dp.message(Command("decline"))
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
        await message.answer("Неверный формат ID.")
        return

    delete_user_and_related(target_id)

    await message.answer(f"Пользователь {target_id} отклонён.")
    log_action(message.from_user.id, f"decline {target_id}")
    try:
        await bot.send_message(target_id, "Ваш запрос отклонён, вы удалены.")
    except:
        pass

###############################################################################
# "Список запросов" (неодобренных), "Список пользователей"
###############################################################################
@dp.message(lambda msg: msg.text in {"Список запросов", "Список запросов (регистрация)"})
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

@dp.message(lambda msg: msg.text in {"Список сотрудников", "Список пользователей"})
async def list_approved_users(message: types.Message):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
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
            role_label = "админ" if role == "admin" else "участник"
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

@dp.message(lambda msg: msg.text == "Список администраторов группы")
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
# Группы (суперадмин)
###############################################################################
class GroupCreateFSM(StatesGroup):
    waiting_for_name = State()


@dp.message(lambda msg: msg.text == "Создать группу")
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


@dp.message(GroupCreateFSM.waiting_for_name)
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


@dp.message(lambda msg: msg.text == "Список групп")
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
@dp.message(lambda msg: msg.text == "Удалить группу")
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

@dp.callback_query(lambda c: c.data.startswith("del_group_pick:"))
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

@dp.callback_query(lambda c: c.data.startswith("del_group_confirm:"))
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

@dp.callback_query(lambda c: c.data == "del_group_cancel")
async def delete_group_cancel(cb: CallbackQuery):
    await cb.message.answer("Удаление группы отменено.")
    await cb.answer()

###############################################################################
# Суперадмин: изменить имя пользователя / показать @username
###############################################################################
class SuperadminChangeNameFSM(StatesGroup):
    waiting_for_user = State()
    waiting_for_fullname = State()


class SuperadminShowUsernameFSM(StatesGroup):
    waiting_for_user = State()


@dp.message(lambda msg: msg.text == "Изменить имя пользователя")
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


@dp.callback_query(lambda c: c.data.startswith("sa_name_user:"), SuperadminChangeNameFSM.waiting_for_user)
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


@dp.message(SuperadminChangeNameFSM.waiting_for_fullname)
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
    except:
        pass
    log_action(message.from_user.id, f"superadmin_change_name {user_id}")
    await state.clear()


@dp.message(lambda msg: msg.text == "Показать @username")
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


@dp.callback_query(lambda c: c.data.startswith("sa_uname_user:"), SuperadminShowUsernameFSM.waiting_for_user)
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
@dp.message(lambda msg: msg.text == "Удалить пользователя из бота")
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
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"del_bot_user_pick:{uid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите пользователя для удаления из бота:", reply_markup=inline_kb)

@dp.callback_query(lambda c: c.data.startswith("del_bot_user_pick:"))
async def superadmin_delete_user_confirm(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    if user_id == cb.from_user.id:
        await cb.answer(TEXT_CANNOT_DELETE_SELF, show_alert=True)
        return

    fullname = get_user_fullname(user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Удалить", callback_data=f"del_bot_user_confirm:{user_id}"),
        InlineKeyboardButton(text=TEXT_CANCEL_BUTTON, callback_data="del_bot_user_cancel")
    ]])
    await cb.message.answer(
        f"Подтвердите удаление пользователя: {fullname}",
        reply_markup=kb
    )
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("del_bot_user_confirm:"))
async def superadmin_delete_user_execute(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    if user_id == cb.from_user.id:
        await cb.answer(TEXT_CANNOT_DELETE_SELF, show_alert=True)
        return

    fullname = get_user_fullname(user_id)

    delete_user_and_related(user_id)

    log_action(cb.from_user.id, f"delete_user_from_bot {user_id}")
    await cb.message.answer(f"Пользователь удалён из бота: {fullname}", reply_markup=get_role_menu(cb.from_user.id))
    try:
        await bot.send_message(user_id, "Ваш аккаунт удалён из бота администратором.")
    except:
        pass
    await cb.answer()

@dp.callback_query(lambda c: c.data == "del_bot_user_cancel")
async def superadmin_delete_user_cancel(cb: CallbackQuery):
    await cb.message.answer("Удаление пользователя отменено.")
    await cb.answer()


class GroupAdminAssignFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@dp.message(lambda msg: msg.text in {"Назначить админа группы", "Назначить администратора группы"})
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


@dp.callback_query(lambda c: c.data.startswith("ga_group:"), GroupAdminAssignFSM.waiting_for_group)
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


@dp.callback_query(lambda c: c.data.startswith("ga_user:"), GroupAdminAssignFSM.waiting_for_user)
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
            except:
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
        except:
            pass
    await cb.message.answer(msg, reply_markup=get_role_menu(cb.from_user.id))
    await cb.answer()
    await state.clear()


class GroupAdminRevokeFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@dp.message(lambda msg: msg.text in {"Отозвать администратора группы", "Отозвать админа группы"})
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


@dp.callback_query(lambda c: c.data.startswith("gar_group:"), GroupAdminRevokeFSM.waiting_for_group)
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


@dp.callback_query(lambda c: c.data.startswith("gar_user:"), GroupAdminRevokeFSM.waiting_for_user)
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
    except:
        pass
    await cb.answer()
    await state.clear()


class GroupAddUserFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@dp.message(lambda msg: msg.text == "Добавить пользователя в группу")
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


@dp.callback_query(lambda c: c.data.startswith("gm_group:"), GroupAddUserFSM.waiting_for_group)
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


@dp.callback_query(lambda c: c.data.startswith("gm_user:"), GroupAddUserFSM.waiting_for_user)
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
        except:
            pass
    await cb.message.answer(msg, reply_markup=get_role_menu(cb.from_user.id))
    await cb.answer()
    await state.clear()


class GroupRemoveUserFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@dp.message(lambda msg: msg.text == "Удалить пользователя из группы" and is_superadmin(msg.from_user.id))
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


@dp.callback_query(lambda c: c.data.startswith("grm_group:"), GroupRemoveUserFSM.waiting_for_group)
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


@dp.callback_query(lambda c: c.data.startswith("grm_user:"), GroupRemoveUserFSM.waiting_for_user)
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
    except:
        pass
    await cb.answer()
    await state.clear()


###############################################################################
# Заявки в группу (админ группы / суперадмин)
###############################################################################
@dp.message(lambda msg: msg.text in {"Заявки на вступление", "Заявки на выход"})
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


@dp.callback_query(lambda c: c.data.startswith("grp_req_approve:") or c.data.startswith("grp_req_decline:"))
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
        except:
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
    except:
        pass
    await cb.answer()
    log_action(user_id, f"group_request declined {req_id}")

###############################################################################
# Сменить рабочую группу (админ/суперадмин)
###############################################################################
@dp.message(lambda msg: msg.text == "Сменить группу")
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

@dp.message(lambda msg: msg.text == "Глобально")
async def set_work_group_global(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    set_last_group_id(message.from_user.id, None)
    await message.answer(TEXT_WORK_GROUP_RESET_GLOBAL, reply_markup=get_role_menu(message.from_user.id))


@dp.message(lambda msg: msg.text == "Выбрать группу")
async def select_work_group_alias(message: types.Message):
    await change_work_group(message)


@dp.callback_query(lambda c: c.data.startswith("set_group:"))
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
        await cb.answer(TEXT_USER_NOT_FOUND, show_alert=True)
        return

    await cb.message.answer(f"Рабочая группа установлена: {group_name}")
    # Обновим меню после выбора группы
    await cb.message.answer(TEXT_MENU_UPDATED, reply_markup=get_role_menu(user_id))
    await cb.answer()

###############################################################################
# Назначить админом /make_admin, Отозвать админа /revoke_admin, Список админов
###############################################################################
@dp.message(lambda msg: msg.text in {"Назначить админом", "Добавить права суперадминистратора"})
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

@dp.callback_query(lambda c: c.data.startswith("make_admin_user:"))
async def callback_make_admin_user(cb: CallbackQuery):
    """
    Шаг 2: админ выбрал конкретного пользователя — делаем его админом.
    """
    if not is_user_admin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    user_id_str = cb.data.split(":")[1]
    user_id = int(user_id_str)

    # Одобряем + is_admin=1
    promote_to_admin(user_id)

    await cb.message.answer(f"Пользователь {get_user_fullname(user_id)} теперь администратор.")
    log_action(cb.from_user.id, f"make_admin {user_id}")

    # Уведомим
    try:
        await bot.send_message(user_id, "Вам назначены права администратора!", reply_markup=get_role_menu(user_id))
    except:
        pass

    await cb.answer()

@dp.message(lambda msg: msg.text in {"Отозвать админа", "Отозвать права суперадминистратора"})
async def pick_admin_to_revoke(message: types.Message):
    """
    Шаг 1: админ нажимает "Отозвать админа".
    Бот показывает список пользователей, у которых is_admin=1 (кроме себя, если хотите).
    """
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return

    # Можем исключить из списка самого себя, если хотите
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

@dp.callback_query(lambda c: c.data.startswith("revoke_admin_user:"))
async def callback_revoke_admin_user(cb: CallbackQuery):
    """
    Шаг 2: выбран конкретный админ, у которого отзываем права.
    """
    if not is_user_admin(cb.from_user.id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
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
    except:
        pass

    await cb.answer()

@dp.message(lambda msg: msg.text in {"Список админов", "Список суперадминистраторов"})
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
# Удалить пользователя из группы
###############################################################################
@dp.message(lambda msg: msg.text == "Удалить пользователя из группы" and not is_superadmin(msg.from_user.id))
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

    # NEW: кнопка «Отмена»
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

@dp.callback_query(lambda c: c.data.startswith("remove_user:"))
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
    except:
        pass
    await cb.answer()

###############################################################################
# FSM для добавления отсутствия
###############################################################################
class AbsenceRequestFSM(StatesGroup):
    waiting_for_category = State()
    waiting_for_start_date = State()
    waiting_for_end_date = State()
    waiting_for_comment = State()

@dp.message(lambda msg: msg.text == "Добавить отсутствие")
async def add_absence_start(message: types.Message, state: FSMContext):
    if not user_exists_in_db(message.from_user.id):
        await message.answer(TEXT_NOT_REGISTERED_SHORT)
        return
    if not is_user_approved(message.from_user.id):
        await message.answer(TEXT_NOT_APPROVED_SHORT)
        return
    if not is_superadmin(message.from_user.id) and not user_has_any_group(message.from_user.id):
        await message.answer(TEXT_NOT_IN_ANY_GROUP)
        return

    # 1) Создадим Reply-клавиатуру с кнопкой «Отмена»
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXT_CANCEL_BUTTON)]
        ],
        resize_keyboard=True
    )

    # 2) Сообщим пользователю, что можно прервать действие
    await message.answer(
        f"Сейчас вы добавляете отсутствие.\n{TEXT_CANCEL_HINT_GENERIC}",
        reply_markup=cancel_kb
    )

    # 3) Теперь отправим ему Inline-кнопки для выбора категории
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отпуск", callback_data="cat_vacation"),
            InlineKeyboardButton(text="Больничный", callback_data="cat_sick"),
        ],
        [
            InlineKeyboardButton(text="DayOff", callback_data="cat_dayoff"),
            InlineKeyboardButton(text="Другое", callback_data="cat_other"),
        ]
    ])
    await message.answer(
        TEXT_SELECT_ABSENCE_CATEGORY,
        reply_markup=kb
    )

    await state.set_state(AbsenceRequestFSM.waiting_for_category)
    
@dp.callback_query(lambda c: c.data.startswith("cat_"), AbsenceRequestFSM.waiting_for_category)
async def process_category_choice(cb: CallbackQuery, state: FSMContext):
    category = cb.data.split("cat_")[1]
    await state.update_data(category=category)
    await cb.message.answer(f"Вы выбрали {category}. Введите дату начала (дд.мм.гггг):")
    await state.set_state(AbsenceRequestFSM.waiting_for_start_date)
    await cb.answer()

@dp.message(AbsenceRequestFSM.waiting_for_start_date)
async def process_start_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_FORMAT)
        return

    await state.update_data(start_date=str(date_obj))
    await message.answer(TEXT_ENTER_END_DATE)
    await state.set_state(AbsenceRequestFSM.waiting_for_end_date)

@dp.message(AbsenceRequestFSM.waiting_for_end_date)
async def process_end_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата.")
        return

    data = await state.get_data()
    start_date_str = data["start_date"]
    start_date_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    if date_obj < start_date_obj:
        await message.answer(TEXT_END_DATE_BEFORE_START)
        return

    await state.update_data(end_date=str(date_obj))
    await message.answer(TEXT_ENTER_COMMENT)
    await state.set_state(AbsenceRequestFSM.waiting_for_comment)

@dp.message(AbsenceRequestFSM.waiting_for_comment)
async def process_comment(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    data = await state.get_data()
    cat = data["category"]
    sd = data["start_date"]
    ed = data["end_date"]

    abs_id = create_absence(user_id, cat, sd, ed, comment, "pending")

    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)

    await message.answer(
        f"Заявка #{abs_id} на отсутствие '{cat}' с {sd_disp} по {ed_disp}\n"
        f"Комментарий: {comment or '—'}\nОтправлена на рассмотрение."
    )
    log_action(user_id, f"Requested absence {abs_id}: {cat} {sd}-{ed}")

    # Уведомим админов групп пользователя и суперадминов
    admin_ids = set(get_admins())
    for gid, _name, _role in get_user_groups(user_id):
        admin_ids.update(get_group_admins(gid))
    for admin_id in admin_ids:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"approve_abs:{abs_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"decline_abs:{abs_id}")
            ]
        ])
        text_admin = (
            f"{get_user_fullname(user_id)} добавил заявку #{abs_id}:\n"
            f"{cat} {sd_disp}–{ed_disp}\n"
            f"Комментарий: {comment or '—'} (pending)"
        )
        try:
            await bot.send_message(admin_id, text_admin, reply_markup=kb)
        except:
            pass

    await message.answer(
        "Отсутствие успешно добавлено! Возвращаю вас в меню.",
        reply_markup=get_role_menu(message.from_user.id)
    )

    await state.clear()

###############################################################################
# "Мои отсутствия"
###############################################################################
class EditAbsenceFSM(StatesGroup):
    waiting_for_new_category = State()
    waiting_for_new_start_date = State()
    waiting_for_new_end_date = State()
    waiting_for_new_comment = State()

@dp.message(lambda msg: msg.text in {"Показать мои отсутствия", "Мои заявки"})
async def show_my_absences(message: types.Message):
    user_id = message.from_user.id
    if not is_user_approved(user_id):
        await message.answer("Вы не одобрены.")
        return
    if not is_superadmin(user_id) and not user_has_any_group(user_id):
        await message.answer(TEXT_NOT_IN_ANY_GROUP)
        return

    rows = list_user_absences(user_id)

    if not rows:
        await message.answer("У вас нет заявок на отсутствие.")
        return

    lines = []
    kb_rows = []
    for (abs_id, cat, sd, ed, cmnt, st) in rows:
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        line = f"#{abs_id} — {cat}, {sd_disp}–{ed_disp}, статус={st}, коммент: {cmnt or '—'}"
        lines.append(line)
        if st == "approved":
            kb_rows.append([
                InlineKeyboardButton(
                    text=f"Удалить #{abs_id}",
                    callback_data=f"request_del:{abs_id}"
                ),
                InlineKeyboardButton(
                    text=f"Изменить #{abs_id}",
                    callback_data=f"request_edit:{abs_id}"
                )
            ])

    text_report = "Ваши заявки:\n" + "\n".join(lines)
    if kb_rows:
        inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    else:
        inline_kb = None

    await message.answer(text_report, reply_markup=inline_kb)

@dp.message(lambda msg: msg.text == "Мои группы")
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


@dp.message(lambda msg: msg.text == "Запроситься в группу")
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


@dp.callback_query(lambda c: c.data.startswith("join_group:"))
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
        except:
            pass


@dp.message(lambda msg: msg.text == "Выйти из группы")
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


@dp.callback_query(lambda c: c.data.startswith("leave_group:"))
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
        except:
            pass

@dp.message(lambda msg: msg.text in {"Удалить мои отсутствия", "Удалить отсутствие"})
async def admin_delete_my_absences(message: types.Message):
    """
    Аналог "Показать мои отсутствия", но другая надпись в меню.
    """
    await show_my_absences(message)

@dp.message(lambda msg: msg.text == "Изменить отсутствие")
async def admin_edit_my_absences_alias(message: types.Message):
    """
    Псевдокнопка: выводим список заявок с кнопками «Изменить».
    """
    await show_my_absences(message)

###############################################################################
# Запрос на удаление одобренного отсутствия
###############################################################################
@dp.callback_query(lambda c: c.data.startswith("request_del:"))
async def request_delete_absence(cb: CallbackQuery):
    abs_id = int(cb.data.split(":")[1])

    row = get_absence_by_id(abs_id)
    if not row:
        await cb.answer("Отсутствие не найдено.", show_alert=True)
        return

    user_id, cat, sd, ed, _cmnt, st = row
    if user_id != cb.from_user.id:
        await cb.answer(TEXT_NOT_YOUR_REQUEST, show_alert=True)
        return
    if st != "approved":
        await cb.answer("Удалять можно только 'approved'.", show_alert=True)
        return

    # Отправим запрос админам групп пользователя и суперадминам
    admin_ids = set(get_admins())
    for gid, _name, _role in get_user_groups(user_id):
        admin_ids.update(get_group_admins(gid))
    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)
    for admin_id in admin_ids:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить удаление", callback_data=f"approve_del:{abs_id}"),
                InlineKeyboardButton(text="Отклонить удаление", callback_data=f"decline_del:{abs_id}")
            ]
        ])
        txt = (
            f"{get_user_fullname(cb.from_user.id)} просит удалить "
            f"заявку #{abs_id} ({cat} {sd_disp}–{ed_disp}, status={st})."
        )
        try:
            await bot.send_message(admin_id, txt, reply_markup=kb)
        except:
            pass

    await cb.message.answer("Запрос на удаление отправлен администратору.")
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("request_edit:"))
async def request_edit_absence(cb: CallbackQuery, state: FSMContext):
    abs_id_str = cb.data.split(":")[1]
    abs_id = int(abs_id_str)

    # Проверим, что заявка существует и принадлежит текущему пользователю
    row = get_absence_by_id(abs_id)
    if not row:
        await cb.answer(TEXT_REQUEST_NOT_FOUND, show_alert=True)
        return

    user_id, cat, sd, ed, cmnt, st = row
    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)
    if user_id != cb.from_user.id:
        await cb.answer(TEXT_NOT_YOUR_REQUEST, show_alert=True)
        return
    if st != "approved":
        await cb.answer("Изменять можно только 'approved'.", show_alert=True)
        return

    # Сохраним abs_id в FSM
    await state.update_data(abs_id=abs_id)

    # Предлагаем новую категорию (inline-кнопки)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отпуск", callback_data="edit_cat_vacation"),
            InlineKeyboardButton(text="Больничный", callback_data="edit_cat_sick"),
        ],
        [
            InlineKeyboardButton(text="DayOff", callback_data="edit_cat_dayoff"),
            InlineKeyboardButton(text="Другое", callback_data="edit_cat_other"),
        ]
    ])
    await cb.message.answer("Выберите новую категорию:", reply_markup=kb)
    await state.set_state(EditAbsenceFSM.waiting_for_new_category)
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_cat_"), EditAbsenceFSM.waiting_for_new_category)
async def edit_category_choice(cb: CallbackQuery, state: FSMContext):
    new_cat = cb.data.split("edit_cat_")[1]
    await state.update_data(new_cat=new_cat)
    await cb.message.answer(TEXT_ENTER_NEW_START_DATE)
    await state.set_state(EditAbsenceFSM.waiting_for_new_start_date)
    await cb.answer()

@dp.message(EditAbsenceFSM.waiting_for_new_start_date)
async def edit_absence_start_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_FORMAT)
        return

    await state.update_data(new_start_date=str(date_obj))
    await message.answer(TEXT_ENTER_NEW_END_DATE)
    await state.set_state(EditAbsenceFSM.waiting_for_new_end_date)

@dp.message(EditAbsenceFSM.waiting_for_new_end_date)
async def edit_absence_end_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_FORMAT)
        return

    data = await state.get_data()
    start_str = data["new_start_date"]
    start_date_obj = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
    if date_obj < start_date_obj:
        await message.answer(TEXT_END_DATE_BEFORE_START)
        return

    await state.update_data(new_end_date=str(date_obj))
    await message.answer(TEXT_ENTER_NEW_COMMENT)
    await state.set_state(EditAbsenceFSM.waiting_for_new_comment)

@dp.message(EditAbsenceFSM.waiting_for_new_comment)
async def edit_absence_comment(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    data = await state.get_data()
    abs_id = data["abs_id"]
    new_cat = data["new_cat"]
    new_sd = data["new_start_date"]
    new_ed = data["new_end_date"]
    user_id = message.from_user.id

    # 1) Считаем из absences старые поля
    old_row = get_absence_by_id(abs_id)
    if not old_row:
        await message.answer(TEXT_ORIGINAL_REQUEST_NOT_FOUND)
        return

    _old_user_id, old_cat, old_sd, old_ed, old_cmnt, _old_status = old_row
    old_sd_disp = format_date_display(old_sd)
    old_ed_disp = format_date_display(old_ed)
    new_sd_disp = format_date_display(new_sd)
    new_ed_disp = format_date_display(new_ed)

    # 2) Записываем в edit_requests
    req_id = create_edit_request(abs_id, new_cat, new_sd, new_ed, comment, user_id)

    # 3) Формируем уведомление админу: "старое" vs "новое"
    old_part = (
        f"Старое:\n"
        f"Категория: {old_cat}\n"
        f"Даты: {old_sd_disp}–{old_ed_disp}\n"
        f"Комментарий: {old_cmnt or '—'}\n\n"
    )
    new_part = (
        f"Новое:\n"
        f"Категория: {new_cat}\n"
        f"Даты: {new_sd_disp}–{new_ed_disp}\n"
        f"Комментарий: {comment or '—'}\n\n"
        f"(pending)"
    )
    text_admin = (
        f"Пользователь {get_user_fullname(user_id)} хочет изменить заявку #{abs_id}.\n\n"
        f"{old_part}{new_part}"
    )

    # 4) Сообщаем пользователю
    await message.answer(
        f"Запрос на изменение заявки #{abs_id} отправлен на одобрение администратору.\n"
        f"(Старое и новое видно админу)."
    )

    # 5) Шлём админам групп пользователя и суперадминам
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Одобрить", callback_data=f"approve_edit:{req_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"decline_edit:{req_id}")
    ]])
    admin_ids = set(get_admins())
    for gid, _name, _role in get_user_groups(user_id):
        admin_ids.update(get_group_admins(gid))
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text_admin, reply_markup=kb)
        except:
            pass

    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("approve_edit:") or c.data.startswith("decline_edit:"))
async def edit_approval_callback(cb: CallbackQuery):
    """
    Хендлер для админа: approve_edit:<req_id> / decline_edit:<req_id>.
    """
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ADMIN_ALERT, show_alert=True)
        return
    if need_select:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    action, req_id_str = cb.data.split(":")
    req_id = int(req_id_str)

    row = get_edit_request(req_id)
    if not row:
        await cb.message.answer("Запрос на изменение не найден.")
        await cb.answer()
        return

    abs_id, new_cat, new_sd, new_ed, new_comment, user_id = row
    if group_id and not user_in_group(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    # Считываем старые поля (если хотите показать «старое → новое» админу)
    old_row = get_absence_by_id(abs_id)
    if not old_row:
        await cb.message.answer(TEXT_ORIGINAL_REQUEST_NOT_FOUND)
        await cb.answer()
        return
    _old_user_id, old_cat, old_sd, old_ed, old_cmnt, _old_status = old_row
    old_sd_disp = format_date_display(old_sd)
    old_ed_disp = format_date_display(old_ed)
    new_sd_disp = format_date_display(new_sd)
    new_ed_disp = format_date_display(new_ed)

    if action == "approve_edit":
        # Применяем новые поля
        update_absence(abs_id, new_cat, new_sd, new_ed, new_comment)
        delete_edit_request(req_id)

        # Показываем «старое → новое» админу (при желании)
        old_text = (
            f"Старое:\nКатегория: {old_cat}\n"
            f"Даты: {old_sd_disp}–{old_ed_disp}\n"
            f"Комментарий: {old_cmnt or '—'}"
        )
        new_text = (
            f"Новое:\nКатегория: {new_cat}\n"
            f"Даты: {new_sd_disp}–{new_ed_disp}\n"
            f"Комментарий: {new_comment or '—'}"
        )
        summary = f"Изменение заявки #{abs_id} одобрено.\n\n{old_text}\n\n→ {new_text}"
        await cb.message.answer(summary)

        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"Ваше изменение заявки #{abs_id} одобрено!\n"
                f"Теперь: {new_cat}, {new_sd_disp}–{new_ed_disp}, {new_comment or '—'}"
            )
        except:
            pass

        await cb.answer()

    else:  # "decline_edit"
        # Никакого UPDATE не делаем — просто удаляем запрос
        delete_edit_request(req_id)

        await cb.message.answer(f"Изменение заявки #{abs_id} отклонено.")
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"Ваше изменение заявки #{abs_id} отклонено администратором."
            )
        except:
            pass

        await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("approve_del:") or c.data.startswith("decline_del:"))
async def confirm_delete_absence(cb: CallbackQuery):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if need_select:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    action, abs_id_str = cb.data.split(":")
    abs_id = int(abs_id_str)

    row = get_absence_by_id(abs_id)
    if not row or row[5] != "approved":
        await cb.message.answer("Не найдено или не 'approved'.")
        await cb.answer()
        return

    user_id, cat, sd, ed, _cmnt, _st = row
    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)
    if group_id and not user_in_group(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if action == "approve_del":
        delete_absence(abs_id)
        await cb.message.answer(f"Удаление #{abs_id} одобрено. Запись удалена.")
        log_action(admin_id, f"approve_del absence {abs_id}")
        try:
            await bot.send_message(user_id, f"Админ удалил вашу заявку #{abs_id}.")
        except:
            pass
    else:
        await cb.message.answer(f"Удаление #{abs_id} отклонено.")
        log_action(cb.from_user.id, f"decline_del absence {abs_id}")
        try:
            await bot.send_message(user_id, f"Админ отклонил удаление вашей заявки #{abs_id}.")
        except:
            pass

    await cb.answer()

###############################################################################
# Заявки на отсутствие (pending)
###############################################################################
@dp.message(lambda msg: msg.text in {"Заявки на отсутствие", "Заявки на отсутствие (pending)"})
async def show_absence_requests(message: types.Message):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    # Cancel KB
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        f"Сейчас вы обрабатываете заявки на отсутствие.\n{TEXT_CANCEL_HINT}",
        reply_markup=cancel_kb
    )

    rows = list_pending_absences(group_id)

    if not rows:
        await message.answer("Нет заявок (pending).")
        return

    for row in rows:
        abs_id, uid, cat, sd, ed, cmnt = row
        user_disp = get_user_fullname(uid)
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        text_info = (
            f"Заявка #{abs_id}\n"
            f"От: {user_disp}\n"
            f"Категория: {cat}\n"
            f"Период: {sd_disp}–{ed_disp}\n"
            f"Комментарий: {cmnt or '—'}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"approve_abs:{abs_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"decline_abs:{abs_id}")
            ]
        ])
        await message.answer(text_info, reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("approve_abs:") or c.data.startswith("decline_abs:"))
async def callback_absence_approval(cb: CallbackQuery):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if need_select:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    action, abs_id_str = cb.data.split(":")
    abs_id = int(abs_id_str)

    row = get_absence_by_id(abs_id)
    if not row:
        await cb.answer(TEXT_REQUEST_NOT_FOUND, show_alert=True)
        return

    user_id, cat, sd, ed, cmnt, st = row
    if st != "pending":
        await cb.answer("Эта заявка уже обработана.", show_alert=True)
        return
    if group_id and not user_in_group(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)

    if action == "approve_abs":
        new_status = "approved"
        txt_admin = f"Заявка #{abs_id} одобрена."
        txt_user = f"Ваша заявка #{abs_id} ({cat} {sd_disp}–{ed_disp}) одобрена!"
    else:
        new_status = "declined"
        txt_admin = f"Заявка #{abs_id} отклонена."
        txt_user = f"Ваша заявка #{abs_id} ({cat} {sd_disp}–{ed_disp}) отклонена."

    update_absence_status(abs_id, new_status)

    await cb.message.answer(txt_admin)
    log_action(admin_id, f"{action} absence {abs_id}")

    try:
        await bot.send_message(user_id, txt_user)
    except:
        pass

    await cb.answer()

###############################################################################
# Показать отсутствия пользователя (админ)
###############################################################################
@dp.message(lambda msg: msg.text in {"Посмотреть отсутствия сотрудника", "Показать отсутствия пользователя"})
async def select_user_for_absences(message: types.Message):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    if group_id:
        members = get_group_members(group_id)
        if not members:
            await message.answer(TEXT_GROUP_NO_USERS)
            return
        kb_rows = []
        for (tid, fname, _username, _role) in members:
            kb_rows.append([InlineKeyboardButton(text=fname, callback_data=f"show_abs:{tid}")])
        inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)
        return

    rows = get_approved_users()

    if not rows:
        await message.answer(TEXT_NO_APPROVED_EMPLOYEES)
        return

    kb_rows = []
    for (tid, fname, _username) in rows:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"show_abs:{tid}")
        ])
         
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)

@dp.callback_query(lambda c: c.data.startswith("show_abs:"))
async def cb_show_absences(cb: CallbackQuery):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if need_select:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    user_id = int(cb.data.split(":")[1])
    if group_id and not user_in_group(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    rows = list_user_absences(user_id)

    user_disp = get_user_fullname(user_id)

    if not rows:
        await cb.message.answer(f"У {user_disp} нет заявок.")
        await cb.answer()
        return

    text_report = f"Отсутствия {user_disp}:\n"
    for (_abs_id, cat, sd, ed, cmnt, st) in rows:
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        text_report += f"- {cat} {sd_disp}–{ed_disp}, [{st}], {cmnt or '—'}\n"

    await cb.message.answer(text_report)
    await cb.answer()

###############################################################################
# Удалить отсутствие пользователя (админ)
###############################################################################
@dp.message(lambda msg: msg.text in {"Удалить отсутствие сотрудника", "Удалить отсутствие пользователя"})
async def admin_delete_absence_start(message: types.Message):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return
    if not group_id:
        await message.answer("Для удаления отсутствия выберите рабочую группу (кнопка «Сменить группу»).")
        return

    # NEW
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы удаляете отсутствие пользователя.\nЕсли передумали, нажмите «Отмена».",
        reply_markup=cancel_kb
    )

    members = get_group_members(group_id)
    if not members:
        await message.answer(TEXT_GROUP_NO_USERS)
        return

    kb_rows = []
    for (tid, fname, _username, _role) in members:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"adm_del_pickuser:{tid}")
        ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите пользователя, у которого хотите удалить конкретное отсутствие:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("adm_del_pickuser:"))
async def admin_delete_absences_pickuser(cb: CallbackQuery):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if need_select or not group_id:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    user_id = int(cb.data.split(":")[1])
    if not user_in_group(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    rows = list_user_absences(user_id)

    user_disp = get_user_fullname(user_id)

    if not rows:
        await cb.message.answer(f"У {user_disp} нет заявок.")
        await cb.answer()
        return

    text_rep = f"Отсутствия {user_disp}:\n"
    kb_rows = []
    for (abs_id, cat, sd, ed, cmnt, st) in rows:
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        text_rep += f"#{abs_id} {cat} {sd_disp}–{ed_disp}, [{st}], {cmnt or '—'}\n"
        kb_rows.append([InlineKeyboardButton(
            text=f"Удалить #{abs_id}",
            callback_data=f"adm_del_abs:{abs_id}"
        )])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer(text_rep + "\nНажмите «Удалить #ID» для удаления.", reply_markup=inline_kb)
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("adm_del_abs:"))
async def admin_delete_absence_final(cb: CallbackQuery):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if need_select or not group_id:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    abs_id = int(cb.data.split(":")[1])

    row = get_absence_by_id(abs_id)
    if not row:
        await cb.answer("Не найдено или уже удалено.", show_alert=True)
        return

    user_id, cat, sd, ed, _cmnt, _st = row
    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)
    if group_id and not user_in_group(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    delete_absence(abs_id)

    await cb.message.answer(f"Отсутствие #{abs_id} ({cat} {sd_disp}–{ed_disp}) удалено админом.")
    log_action(cb.from_user.id, f"adm_del_abs {abs_id}")

    try:
        await bot.send_message(user_id, f"Админ удалил ваше отсутствие #{abs_id} ({cat} {sd_disp}–{ed_disp}).")
    except:
        pass

    await cb.answer()

###############################################################################
# Изменить отсутствие пользователя (админ)
###############################################################################
class AdminEditAbsenceFSM(StatesGroup):
    waiting_for_user = State()
    waiting_for_absence = State()
    waiting_for_category = State()
    waiting_for_start_date = State()
    waiting_for_end_date = State()
    waiting_for_comment = State()


@dp.message(lambda msg: msg.text in {"Изменить отсутствие сотрудника", "Изменить отсутствие пользователя"})
async def admin_edit_absence_start(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    await state.clear()
    await state.update_data(group_id=group_id)

    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        f"Сейчас вы редактируете отсутствие пользователя.\n{TEXT_CANCEL_HINT}",
        reply_markup=cancel_kb
    )

    if group_id:
        members = get_group_members(group_id)
        if not members:
            await message.answer(TEXT_GROUP_NO_USERS)
            return
        kb_rows = []
        for (tid, fname, _username, _role) in members:
            kb_rows.append([InlineKeyboardButton(text=fname, callback_data=f"adm_edit_user:{tid}")])
        inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)
        await state.set_state(AdminEditAbsenceFSM.waiting_for_user)
        return

    # Глобально (суперадмин)
    users = get_approved_users()
    if not users:
        await message.answer(TEXT_NO_APPROVED_EMPLOYEES)
        return

    kb_rows = []
    for uid, fullname, username in users:
        label = fullname
        if username:
            label += f" (@{username})"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"adm_edit_user:{uid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)
    await state.set_state(AdminEditAbsenceFSM.waiting_for_user)


@dp.callback_query(lambda c: c.data.startswith("adm_edit_user:"), AdminEditAbsenceFSM.waiting_for_user)
async def admin_edit_absence_pick_user(cb: CallbackQuery, state: FSMContext):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if need_select:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_USER, show_alert=True)
        return

    if group_id and not user_in_group(user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    rows = list_user_absences(user_id)

    if not rows:
        await cb.message.answer("У сотрудника нет заявок.")
        await cb.answer()
        await state.clear()
        return

    await state.update_data(target_user_id=user_id)
    kb_rows = []
    for abs_id, cat, sd, ed, cmnt, st in rows:
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        label = f"#{abs_id} {cat} {sd_disp}–{ed_disp} [{st}]"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"adm_edit_abs:{abs_id}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer("Выберите заявку для изменения:", reply_markup=inline_kb)
    await state.set_state(AdminEditAbsenceFSM.waiting_for_absence)
    await cb.answer()


@dp.callback_query(lambda c: c.data.startswith("adm_edit_abs:"), AdminEditAbsenceFSM.waiting_for_absence)
async def admin_edit_absence_pick_absence(cb: CallbackQuery, state: FSMContext):
    admin_id = cb.from_user.id
    allowed, group_id, need_select = get_admin_scope(admin_id)
    if not allowed:
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return
    if need_select:
        await cb.answer(TEXT_SELECT_GROUP_FIRST_ALERT, show_alert=True)
        return

    try:
        abs_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer(TEXT_INVALID_REQUEST, show_alert=True)
        return

    row = get_absence_by_id(abs_id)
    if not row:
        await cb.answer(TEXT_REQUEST_NOT_FOUND, show_alert=True)
        return

    target_user_id, cat, sd, ed, cmnt, st = row
    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)
    if group_id and not user_in_group(target_user_id, group_id):
        await cb.answer(TEXT_NO_RIGHTS_ALERT, show_alert=True)
        return

    await state.update_data(abs_id=abs_id, target_user_id=target_user_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отпуск", callback_data="adm_edit_cat_vacation"),
            InlineKeyboardButton(text="Больничный", callback_data="adm_edit_cat_sick"),
        ],
        [
            InlineKeyboardButton(text="DayOff", callback_data="adm_edit_cat_dayoff"),
            InlineKeyboardButton(text="Другое", callback_data="adm_edit_cat_other"),
        ]
    ])
    await cb.message.answer(
        f"Текущие данные: {cat} {sd_disp}–{ed_disp}, коммент: {cmnt or '—'}, статус={st}\n"
        f"Выберите новую категорию (можно выбрать ту же):",
        reply_markup=kb
    )
    await state.set_state(AdminEditAbsenceFSM.waiting_for_category)
    await cb.answer()


@dp.callback_query(lambda c: c.data.startswith("adm_edit_cat_"), AdminEditAbsenceFSM.waiting_for_category)
async def admin_edit_absence_category(cb: CallbackQuery, state: FSMContext):
    new_cat = cb.data.split("adm_edit_cat_")[1]
    await state.update_data(new_cat=new_cat)
    await cb.message.answer(TEXT_ENTER_NEW_START_DATE)
    await state.set_state(AdminEditAbsenceFSM.waiting_for_start_date)
    await cb.answer()


@dp.message(AdminEditAbsenceFSM.waiting_for_start_date)
async def admin_edit_absence_start_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_FORMAT)
        return

    await state.update_data(new_start_date=str(date_obj))
    await message.answer(TEXT_ENTER_NEW_END_DATE)
    await state.set_state(AdminEditAbsenceFSM.waiting_for_end_date)


@dp.message(AdminEditAbsenceFSM.waiting_for_end_date)
async def admin_edit_absence_end_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_FORMAT)
        return

    data = await state.get_data()
    start_str = data["new_start_date"]
    start_date_obj = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
    if date_obj < start_date_obj:
        await message.answer(TEXT_END_DATE_BEFORE_START)
        return

    await state.update_data(new_end_date=str(date_obj))
    await message.answer(TEXT_ENTER_NEW_COMMENT)
    await state.set_state(AdminEditAbsenceFSM.waiting_for_comment)


@dp.message(AdminEditAbsenceFSM.waiting_for_comment)
async def admin_edit_absence_comment(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    data = await state.get_data()
    abs_id = data["abs_id"]
    new_cat = data["new_cat"]
    new_sd = data["new_start_date"]
    new_ed = data["new_end_date"]
    target_user_id = data["target_user_id"]

    old_row = get_absence_by_id(abs_id)
    if not old_row:
        await message.answer(TEXT_ORIGINAL_REQUEST_NOT_FOUND)
        await state.clear()
        return

    _old_user_id, old_cat, old_sd, old_ed, old_cmnt, old_status = old_row
    old_sd_disp = format_date_display(old_sd)
    old_ed_disp = format_date_display(old_ed)
    new_sd_disp = format_date_display(new_sd)
    new_ed_disp = format_date_display(new_ed)
    update_absence(abs_id, new_cat, new_sd, new_ed, comment)

    await message.answer(
        f"Заявка #{abs_id} обновлена.\n"
        f"Было: {old_cat} {old_sd_disp}–{old_ed_disp}, {old_cmnt or '—'}\n"
        f"Стало: {new_cat} {new_sd_disp}–{new_ed_disp}, {comment or '—'}"
    )

    try:
        await bot.send_message(
            target_user_id,
            f"Администратор изменил вашу заявку #{abs_id}.\n"
            f"Теперь: {new_cat} {new_sd_disp}–{new_ed_disp}, {comment or '—'}"
        )
    except:
        pass

    log_action(message.from_user.id, f"admin_edit_absence {abs_id}")
    await message.answer(TEXT_BACK_TO_MENU, reply_markup=get_role_menu(message.from_user.id))
    await state.clear()

###############################################################################
# ВЫГРУЗКА CSV ЗА ПЕРИОД
###############################################################################
class CsvExportFSM(StatesGroup):
    waiting_for_start_date = State()
    waiting_for_end_date = State()

@dp.message(lambda msg: msg.text in {"Выгрузить отсутствия (CSV)", "Выгрузить отсутствия в CSV"})
async def start_csv_export(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    await state.clear()  # optional if you want to ensure no leftover states
    await state.update_data(group_id=group_id)

    # NEW: create "Cancel" reply keyboard
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        f"Сейчас вы собираетесь выгрузить отсутствия (CSV).\n{TEXT_ENTER_PERIOD_START_OR_CANCEL}",
        reply_markup=cancel_kb
    )

    await state.set_state(CsvExportFSM.waiting_for_start_date)

@dp.message(CsvExportFSM.waiting_for_start_date)
async def csv_export_start_date(message: types.Message, state: FSMContext):
    if message.text == TEXT_CANCEL_BUTTON:
        await state.clear()
        await message.answer(
            TEXT_CANCELLED,
            reply_markup=get_role_menu(message.from_user.id)
        )
        return

    text = message.text.strip()
    try:
        start_date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Попробуйте снова.")
        return

    await state.update_data(start_date=str(start_date_obj))
    await message.answer("Введите дату окончания периода (дд.мм.гггг):")
    await state.set_state(CsvExportFSM.waiting_for_end_date)

@dp.message(CsvExportFSM.waiting_for_end_date)
async def csv_export_end_date(message: types.Message, state: FSMContext):
    if message.text == TEXT_CANCEL_BUTTON:
        await state.clear()
        await message.answer(
            TEXT_CANCELLED,
            reply_markup=get_role_menu(message.from_user.id)
        )
        return

    text = message.text.strip()
    try:
        end_date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Введите в формате дд.мм.гггг, например 15.06.2025.")
        return  # Не сбрасываем state, даём ввести снова

    data = await state.get_data()
    start_date_str = data["start_date"]
    group_id = data.get("group_id")
    start_date_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()

    if end_date_obj < start_date_obj:
        await message.answer("Дата окончания не может быть раньше даты начала. Попробуйте снова.")
        return  # Не сбрасываем state, остаёмся в этом состоянии

    # теперь идёт твоя логика для формирования CSV...
    await state.update_data(end_date=str(end_date_obj))
    sds = str(start_date_obj)
    eds = str(end_date_obj)
    sds_disp = format_date_display(sds)
    eds_disp = format_date_display(eds)

    # Выбираем approved-отсутствия, пересекающие [sds; eds]
    rows = list_approved_absences_between(sds, eds, group_id)

    logging.debug(f"Found {len(rows)} rows for CSV export from {sds} to {eds}")

    if not rows:
        await message.answer(f"Нет 'approved' отсутствий в период {sds_disp}–{eds_disp}.")
        await state.clear()
        return

    # Формируем CSV
    # Заменяем telegram_id на fullname;username
    lines = ["fullname;username;category;start_date;end_date;comment"]
    for (uid, cat, sd, ed, cmnt, fname, uname) in rows:
        cmnt_esc = (cmnt or "").replace(";", ",")
        # fullname + (@username), если username есть
        if uname:
            user_str = f"{fname} (@{uname})"
        else:
            user_str = f"{fname}"
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        lines.append(f"{user_str};{uname or ''};{cat};{sd_disp};{ed_disp};{cmnt_esc}")

    logging.debug(f"CSV lines count (including header): {len(lines)}")

    csv_text = "\n".join(lines)
    from io import BytesIO
    from aiogram.types import BufferedInputFile
    bom = b'\xef\xbb\xbf'  # UTF-8 BOM
    csv_bytes = bom + csv_text.encode('utf-8')
    buf = BytesIO(csv_bytes)
    buf.seek(0)
    input_file = BufferedInputFile(buf.getvalue(), filename=f"absences_{sds_disp}_{eds_disp}.csv")

    await message.answer_document(document=input_file, caption="CSV-выгрузка.")

    log_action(message.from_user.id, f"Export CSV {sds}-{eds}")
    await message.answer(
        "Выгрузка завершена! Возвращаю вас в админ-меню.",
        reply_markup=get_role_menu(message.from_user.id)
    )

    await state.clear()

###################################
# ВЫГРУЗКА ОТСУТСТВИЙ ЗА СЕГОДНЯ
######################################

@dp.message(lambda msg: msg.text in {"Выгрузить отсутствия за сегодня", "Отсутствия на сегодня"})
async def show_absences_today(message: types.Message):
    """
    Показываем список одобренных отсутствий, которые пересекаются с 'сегодня'.
    """
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    # 'today_display' вместо 'today_str', в формате дд.мм.гггг
    today_display = datetime.date.today().strftime("%d.%m.%Y")

   # Для сравнения в WHERE нужен формат YYYY-MM-DD
    today_iso = datetime.date.today().isoformat()

    # Сегодняшняя дата (YYYY-MM-DD)
    today_str = datetime.date.today().isoformat()

    # Ищем все approved-записи, у которых период пересекается с сегодняшней датой
    # Условие пересечения:
    # start_date <= today <= end_date
    rows = list_approved_absences_for_date(today_iso, group_id)


    if not rows:
        await message.answer(f"На сегодня ({today_display}) нет одобренных отсутствий.")
        return

    # Формируем текст в формате "Фамилия И.О., причина, срок"
    lines = []
    for (uid, category, sd, ed, cmnt, fullname, username) in rows:
        
        start_disp = format_date_display(sd)
        end_disp = format_date_display(ed)
        
        # Если нужно вывести username, можно добавить "(@username)"
        user_str = fullname  # + (f" (@{username})" if username else "")
        #period_str = f"{sd}–{ed}"
        comment_str = cmnt if cmnt else "—"
        line = f"{user_str} ({category}, {start_disp} - {end_disp}), комментарий: {comment_str}"
        lines.append(line)

    result_text = f"Отсутствия на сегодня ({today_display}):\n\n" + "\n\n".join(lines)
    await message.answer(result_text)


    # Если хотите логировать действие:
    log_action(message.from_user.id, f"Выгрузка за сегодня: {today_display}")


################################################
# FSM для "Добавить отсутствие другому пользователю"
################################################
class AddAbsenceForAnotherFSM(StatesGroup):
    waiting_for_user = State()
    waiting_for_category = State()
    waiting_for_start_date = State()
    waiting_for_end_date = State()
    waiting_for_comment = State()


@dp.message(lambda msg: msg.text in {"Добавить отсутствие другому сотруднику", "Добавить отсутствие другому пользователю"})
async def add_absence_for_another_start(message: types.Message, state: FSMContext):
    """
    1) Любой одобренный пользователь нажимает «Добавить отсутствие другому пользователю».
    2) Бот показывает список одобренных пользователей (is_approved=1).
    """
    if not is_user_approved(message.from_user.id):
        await message.answer("Вы не одобрены, не можете добавлять отсутствие другим.")
        return
    if not is_superadmin(message.from_user.id) and not user_has_any_group(message.from_user.id):
        await message.answer(TEXT_NOT_IN_ANY_GROUP)
        return

    # Сбросим текущее состояние, если вдруг пользователь был в другом процессе
    await state.clear()

    # NEW
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        f"Сейчас вы добавляете отсутствие другому пользователю.\n{TEXT_CANCEL_HINT}",
        reply_markup=cancel_kb
    )

    # Собираем список одобренных сотрудников
    rows = get_approved_users()

    if not rows:
        await message.answer("Нет ни одного одобренного сотрудника в системе.")
        return

    # Формируем inline-кнопки для выбора сотрудника
    kb_rows = []
    for (tid, fname, _username) in rows:
        # Кнопка: название = fullname, callback_data = add_for_user:<ID>
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"add_for_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(
        "Выберите сотрудника, которому хотите добавить отсутствие:",
        reply_markup=inline_kb
    )

    # Переходим в состояние waiting_for_user
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_user)


@dp.callback_query(lambda c: c.data.startswith("add_for_user:"), AddAbsenceForAnotherFSM.waiting_for_user)
async def pick_user_for_abs(cb: CallbackQuery, state: FSMContext):
    """
    1) Пользователь выбрал конкретного сотрудника из списка.
    2) Сохраняем target_user_id, переходим к выбору категории.
    """
    if not is_user_approved(cb.from_user.id):
        await cb.answer(TEXT_NOT_APPROVED_SHORT)
        return

    # Извлекаем ID выбранного сотрудника
    user_id_str = cb.data.split(":")[1]
    target_user_id = int(user_id_str)

    await state.update_data(target_user_id=target_user_id)

    # Предлагаем категории — чтобы не путать с "cat_", назовём "another_cat_"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отпуск", callback_data="another_cat_vacation"),
            InlineKeyboardButton(text="Больничный", callback_data="another_cat_sick")
        ],
        [
            InlineKeyboardButton(text="DayOff", callback_data="another_cat_dayoff"),
            InlineKeyboardButton(text="Другое", callback_data="another_cat_other")
        ]
    ])
    await cb.message.answer(TEXT_SELECT_ABSENCE_CATEGORY, reply_markup=kb)
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_category)
    await cb.answer()


@dp.callback_query(lambda c: c.data.startswith("another_cat_"), AddAbsenceForAnotherFSM.waiting_for_category)
async def pick_category_for_another(cb: CallbackQuery, state: FSMContext):
    """
    Сохраняем категорию, просим дату начала (дд.мм.гггг).
    """
    if not is_user_approved(cb.from_user.id):
        await cb.answer(TEXT_NOT_APPROVED_SHORT)
        return

    category = cb.data.split("another_cat_")[1]  # vacation / sick / dayoff / other
    await state.update_data(category=category)

    await cb.message.answer(
        f"Категория выбрана: {category}.\nВведите дату начала (дд.мм.гггг):"
    )
    await cb.answer()
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_start_date)


@dp.message(AddAbsenceForAnotherFSM.waiting_for_start_date)
async def another_absence_start_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_TRY_AGAIN)
        return

    await state.update_data(start_date=str(date_obj))  # Сохраним как 'YYYY-MM-DD'
    await message.answer(TEXT_ENTER_END_DATE)
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_end_date)


@dp.message(AddAbsenceForAnotherFSM.waiting_for_end_date)
async def another_absence_end_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_TRY_AGAIN)
        return

    data = await state.get_data()
    start_date_str = data["start_date"]
    start_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    if date_obj < start_obj:
        await message.answer(TEXT_END_DATE_BEFORE_START)
        return

    await state.update_data(end_date=str(date_obj))
    await message.answer(TEXT_ENTER_COMMENT)
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_comment)


@dp.message(AddAbsenceForAnotherFSM.waiting_for_comment)
async def another_absence_comment(message: types.Message, state: FSMContext):
    # Ввод комментария, запись в БД
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    data = await state.get_data()
    target_user_id = data["target_user_id"]
    category = data["category"]
    sd = data["start_date"]
    ed = data["end_date"]
    sd_disp = format_date_display(sd)
    ed_disp = format_date_display(ed)

    # Можно задать статус='pending' или сразу 'approved', как хотите
    abs_id = create_absence(target_user_id, category, sd, ed, comment, "pending")

    await message.answer(
        f"Отсутствие #{abs_id} добавлено пользователю {get_user_fullname(target_user_id)}.\n"
        f"Категория: {category}, {sd_disp}–{ed_disp}\nКомментарий: {comment or '—'}\nСтатус: pending."
    )
    log_action(message.from_user.id, f"AddAbsForAnother user={target_user_id}, abs_id={abs_id}")

    # При желании уведомляем самого сотрудника:
    try:
        await bot.send_message(
            target_user_id,
            f"Вам добавлено отсутствие #{abs_id} ({category}, {sd_disp}–{ed_disp}) от другого пользователя.\n"
            f"Комментарий: {comment or '—'}\n(статус: pending)"
        )
    except:
        pass

    # ──── ВАЖНО ────
    # Теперь сохраняем user_id: это тот, кто ИНИЦИИРОВАЛ добавление
    user_id = message.from_user.id

    # Уведомим админов групп целевого пользователя и суперадминов
    admin_ids = set(get_admins())
    for gid, _name, _role in get_user_groups(target_user_id):
        admin_ids.update(get_group_admins(gid))
    for admin_id in admin_ids:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"approve_abs:{abs_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"decline_abs:{abs_id}")
            ]
        ])
        text_admin = (
            f"{get_user_fullname(user_id)} добавил заявку #{abs_id} "
            f"ДЛЯ {get_user_fullname(target_user_id)}:\n"
            f"{category} {sd_disp}–{ed_disp}\n"
            f"Комментарий: {comment or '—'} (pending)"
        )
        try:
            await bot.send_message(admin_id, text_admin, reply_markup=kb)
        except:
            pass

    # Логируем (по желанию)
    log_action(user_id, f"AddAbsForAnother user={target_user_id}, abs_id={abs_id}")

    # Сбрасываем FSM
    await state.clear()
    await message.answer(TEXT_BACK_TO_MENU, reply_markup=get_role_menu(message.from_user.id))


#############################################
# Обновить меню
#############################################

async def broadcast_new_menu():
    """
    Рассылает новое меню всем одобренным пользователям.
    """
    # Берём только одобренных (is_approved=1), т.к. не имеет смысла обновлять не одобренным
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
        except Exception as e:
            logging.warning(f"Не удалось отправить меню пользователю {tg_id}: {e}")

    logging.info(f"Обновили меню у {updated_count} пользователей.")

# Команда /refresh_menu, чтобы запустить эту рассылку вручную
@dp.message(Command("refresh_menu"))
async def cmd_refresh_menu(message: types.Message):
    # Проверим права админа, чтобы только админ мог перезапускать обновление
    if not is_user_admin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    await broadcast_new_menu()
    await message.answer("Меню обновлено у всех одобренных пользователей.")

###############################################################################
# Вернуться в меню (reply-кнопка)
###############################################################################
@dp.message(lambda msg: msg.text == BACK_BUTTON_TEXT)
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(TEXT_BACK_TO_MENU, reply_markup=get_role_menu(message.from_user.id))

#######################
# Глобальный хендлер TEXT_CANCEL_BUTTON (Reply-кнопка)
###############################
@dp.message(StateFilter("*"), lambda msg: msg.text == TEXT_CANCEL_BUTTON)
async def cancel_process(message: types.Message, state: FSMContext):
    """
    Если пользователь во время любого состояния FSM нажмёт «Отмена»,
    сбросим состояние и вернём ему меню.
    """
    await state.clear()

    await message.answer(
        TEXT_CANCELLED,
        reply_markup=get_role_menu(message.from_user.id)
    )

###############################################################################
# Fallback
###############################################################################
@dp.message()
async def fallback_handler(message: types.Message):
    tg_id = message.from_user.id
    if not user_exists_in_db(tg_id):
        await message.answer(TEXT_NOT_REGISTERED, reply_markup=not_approved_menu)
        return
    if not is_user_approved(tg_id):
        await message.answer(TEXT_NOT_APPROVED, reply_markup=not_approved_menu)
        return

    await message.answer(TEXT_UNKNOWN_COMMAND, reply_markup=get_role_menu(tg_id))

###############################################################################
# Запуск
###############################################################################
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
