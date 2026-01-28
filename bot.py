import asyncio
import logging
import sqlite3
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

###############################################################################
# ЛОГИРОВАНИЕ
###############################################################################
logging.basicConfig(level=logging.DEBUG)

def log_action(user_id: int, action: str):
    """
    Записываем действие в таблицу logs + выводим в консоль
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (action_time, user_id, action) VALUES (?, ?, ?)",
        (datetime.datetime.now().isoformat(), user_id, action)
    )
    conn.commit()
    conn.close()

    logging.info(f"[LOG_ACTION] user={user_id} | {action}")

###############################################################################
# ИНИЦИАЛИЗАЦИЯ БД И БОТА
###############################################################################
init_db()  # создание таблиц, если нет
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

###############################################################################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ БД
###############################################################################
def user_exists_in_db(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return (row is not None)

def is_user_approved(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return (row is not None) and (row[0] == 1)

def is_user_admin(tg_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return (row is not None) and (row[0] == 1)

def is_superadmin(tg_id: int) -> bool:
    """
    Глобальная роль. Сейчас совпадает с is_admin (переиспользуем колонку).
    """
    return is_user_admin(tg_id)

def get_admins() -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_admin=1")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_last_group_id(tg_id: int) -> int | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT last_group_id FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]

def set_last_group_id(tg_id: int, group_id: int | None) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_group_id=? WHERE telegram_id=?", (group_id, tg_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated

def list_all_groups() -> list[tuple[int, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM groups ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_group_name(group_id: int) -> str | None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name FROM groups WHERE id=?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_groups(tg_id: int) -> list[tuple[int, str, str]]:
    """
    Возвращает список групп пользователя: (group_id, group_name, role).
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT gm.group_id, g.name, gm.role
        FROM group_memberships gm
        JOIN groups g ON g.id = gm.group_id
        WHERE gm.user_id=?
        ORDER BY g.name
    """, (tg_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def user_has_any_group(tg_id: int) -> bool:
    return len(get_user_groups(tg_id)) > 0

def user_is_group_admin_any(tg_id: int) -> bool:
    return any(role == "admin" for _, _, role in get_user_groups(tg_id))

def user_in_group(tg_id: int, group_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM group_memberships WHERE user_id=? AND group_id=?
    """, (tg_id, group_id))
    row = cur.fetchone()
    conn.close()
    return row is not None

def has_pending_group_request(tg_id: int, group_id: int, req_type: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1
        FROM group_requests
        WHERE user_id=? AND group_id=? AND type=? AND status='pending'
    """, (tg_id, group_id, req_type))
    row = cur.fetchone()
    conn.close()
    return row is not None

def is_group_admin(tg_id: int, group_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1
        FROM group_memberships
        WHERE user_id=? AND group_id=? AND role='admin'
    """, (tg_id, group_id))
    row = cur.fetchone()
    conn.close()
    return row is not None

def get_group_admins(group_id: int) -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id
        FROM group_memberships
        WHERE group_id=? AND role='admin'
    """, (group_id,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_approved_users() -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_id, fullname, username
        FROM users
        WHERE is_approved=1
        ORDER BY fullname
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_group_members(group_id: int) -> list[tuple[int, str, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT u.telegram_id, u.fullname, u.username, gm.role
        FROM group_memberships gm
        JOIN users u ON u.telegram_id = gm.user_id
        WHERE gm.group_id=?
        ORDER BY u.fullname
    """, (group_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_user_fullname(tg_id: int) -> str:
    """
    Возвращает fullname + (@username), либо "User <id>", если записи нет.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT fullname, username FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        fullname, username = row
        if username:
            return f"{fullname} (@{username})"
        else:
            return f"{fullname}"
    return f"User {tg_id}"

###############################################################################
# КНОПКИ (ReplyKeyboard)
###############################################################################
not_approved_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Зарегистрироваться")],
    ],
    resize_keyboard=True
)

admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Список запросов"),
            KeyboardButton(text="Список сотрудников")
        ],
        [
            KeyboardButton(text="Заявки в группу")
        ],
        [
            KeyboardButton(text="Заявки на отсутствие"),
            KeyboardButton(text="Выгрузить отсутствия (CSV)")
        ],
        [
            KeyboardButton(text="Назначить админом"),
            KeyboardButton(text="Список админов"),
            KeyboardButton(text="Отозвать админа")
        ],
        [
            KeyboardButton(text="Создать группу"),
            KeyboardButton(text="Список групп")
        ],
        [
            KeyboardButton(text="Назначить админа группы"),
            KeyboardButton(text="Добавить пользователя в группу")
        ],
        [
            KeyboardButton(text="Удалить пользователя из группы")
        ],
        [
            KeyboardButton(text="Добавить отсутствие"),
            KeyboardButton(text="Удалить мои отсутствия")
        ],
        [
            KeyboardButton(text="Посмотреть отсутствия сотрудника"),
            KeyboardButton(text="Удалить сотрудника")
        ],
        [
            KeyboardButton(text="Удалить отсутствие сотрудника"),
            KeyboardButton(text="Выгрузить отсутствия за сегодня")
        ],
        [
            KeyboardButton(text="Добавить отсутствие другому сотруднику") 
        ],
        [
            KeyboardButton(text="Сменить группу")
        ]
    ],
    resize_keyboard=True
)

user_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить отсутствие")],
        [KeyboardButton(text="Мои отсутствия")],
        [KeyboardButton(text="Мои группы")],
        [KeyboardButton(text="Запроситься в группу")],
        [KeyboardButton(text="Выйти из группы")],
        [KeyboardButton(text="Добавить отсутствие другому сотруднику")]
    ],
    resize_keyboard=True
)

group_admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Заявки в группу")],
        [KeyboardButton(text="Добавить отсутствие")],
        [KeyboardButton(text="Мои отсутствия")],
        [KeyboardButton(text="Мои группы")],
        [KeyboardButton(text="Запроситься в группу")],
        [KeyboardButton(text="Выйти из группы")],
        [KeyboardButton(text="Добавить отсутствие другому сотруднику")],
        [KeyboardButton(text="Сменить группу")]
    ],
    resize_keyboard=True
)

no_group_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Запроситься в группу")]
    ],
    resize_keyboard=True
)

def get_role_menu(tg_id: int) -> ReplyKeyboardMarkup:
    if is_superadmin(tg_id):
        return admin_menu
    groups = get_user_groups(tg_id)
    if not groups:
        return no_group_menu
    if any(role == "admin" for _, _, role in groups):
        return group_admin_menu
    return user_menu

###############################################################################
# /start
###############################################################################
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    tg_id = message.from_user.id

    if not user_exists_in_db(tg_id):
        await message.answer(
            "Вы не зарегистрированы! Нажмите «Зарегистрироваться», чтобы подать заявку.",
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
            "Подайте заявку на вступление.",
            reply_markup=no_group_menu
        )
        return

    if is_superadmin(tg_id):
        await message.answer("Здравствуйте, Суперадминистратор!", reply_markup=admin_menu)
    elif user_is_group_admin_any(tg_id):
        await message.answer("Здравствуйте, Администратор группы!", reply_markup=group_admin_menu)
    else:
        await message.answer("Добро пожаловать, Пользователь!", reply_markup=user_menu)

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
        await message.answer("Пустое значение. Попробуйте снова.")
        return

    tg_id = message.from_user.id
    username = message.from_user.username or ""
    log_action(tg_id, f"Регистрация. Указал ФИО: {fullname}")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Если запись уже существует, обновим
    cur.execute("SELECT 1 FROM users WHERE telegram_id=?", (tg_id,))
    row = cur.fetchone()

    if row:
        cur.execute("""
            UPDATE users
            SET username=?, fullname=?, is_approved=0
            WHERE telegram_id=?
        """, (username, fullname, tg_id))
    else:
        cur.execute("""
            INSERT INTO users (telegram_id, username, fullname, is_approved, is_admin)
            VALUES (?, ?, ?, 0, 0)
        """, (tg_id, username, fullname))

    conn.commit()
    conn.close()

    await message.answer("Спасибо! Ваша заявка отправлена администратору.")
    if is_user_admin(message.from_user.id):
        await message.answer(
            "Отсутствие успешно добавлено! Возвращаю вас в админ-меню.",
            reply_markup=admin_menu
        )
    else:
        await message.answer(
            "Отсутствие успешно добавлено! Возвращаю вас в пользовательское меню.",
            reply_markup=user_menu
        )

    await state.clear()
    
    # NEW: create a Cancel reply KB
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы добавляете отсутствие другому сотруднику.\n"
        "Если ошиблись, нажмите «Отмена», чтобы прервать.",
        reply_markup=cancel_kb
    )

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
        await cb.answer("Нет прав админа!", show_alert=True)
        return

    action, user_id_str = cb.data.split(":")
    user_id = int(user_id_str)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE telegram_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        await cb.answer("Пользователь не найден.", show_alert=True)
        conn.close()
        return

    if action == "approve_user":
        if row[0] == 1:
            await cb.answer("Этот пользователь уже одобрен.", show_alert=True)
            conn.close()
            return
        cur.execute("UPDATE users SET is_approved=1 WHERE telegram_id=?", (user_id,))
        conn.commit()
        conn.close()

        fname = get_user_fullname(user_id)
        await cb.message.answer(f"{fname} — теперь одобрен.")
        log_action(cb.from_user.id, f"approve_user {user_id}")
        await cb.answer()

        try:
            if is_user_admin(user_id):
                await bot.send_message(user_id, "Ваш запрос одобрен (админ-меню)!", reply_markup=admin_menu)
            else:
                await bot.send_message(user_id, "Ваш запрос одобрен!", reply_markup=user_menu)
        except:
            pass

    else:  # decline_user
        if row[0] == 1:
            await cb.answer("Этот пользователь уже одобрен, отклонение не имеет смысла.", show_alert=True)
            conn.close()
            return

        cur.execute("DELETE FROM users WHERE telegram_id=?", (user_id,))
        conn.commit()
        conn.close()

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
        await message.answer("Нет прав.")
        return

    # Cancel KB
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы удаляете сотрудника.\n"
        "Если передумали, нажмите «Отмена».",
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

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_approved=1 WHERE telegram_id=?", (target_id,))
    conn.commit()
    conn.close()

    await message.answer(f"Пользователь {target_id} одобрен.")
    log_action(message.from_user.id, f"approve {target_id}")
    try:
        if is_user_admin(target_id):
            await bot.send_message(target_id, "Ваш запрос одобрен (админ)!", reply_markup=admin_menu)
        else:
            await bot.send_message(target_id, "Ваш запрос одобрен!", reply_markup=user_menu)
    except:
        pass

@dp.message(Command("decline"))
async def cmd_decline(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав.")
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

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE telegram_id=?", (target_id,))
    conn.commit()
    conn.close()

    await message.answer(f"Пользователь {target_id} отклонён.")
    log_action(message.from_user.id, f"decline {target_id}")
    try:
        await bot.send_message(target_id, "Ваш запрос отклонён, вы удалены.")
    except:
        pass

###############################################################################
# "Список запросов" (неодобренных), "Список сотрудников"
###############################################################################
@dp.message(lambda msg: msg.text == "Список запросов")
async def list_pending_users(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_approved=0")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет заявок на одобрение.")
        return

    text_list = "Ожидают одобрения:\n"
    kb_rows = []
    for (tid,) in rows:
        disp = get_user_fullname(tid)
        text_list += f"- {disp}\n"
        kb_rows.append([InlineKeyboardButton(text=disp, callback_data=f"dummy:{tid}")])
        kb_rows.append([
            InlineKeyboardButton(text="Одобрить", callback_data=f"approve_user:{tid}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"decline_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(text_list, reply_markup=inline_kb)

@dp.message(lambda msg: msg.text == "Список сотрудников")
async def list_approved_users(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
    SELECT telegram_id, fullname
    FROM users
    WHERE is_approved=1
    ORDER BY fullname
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет одобренных сотрудников.")
        return

    text_list = "Одобренные сотрудники:\n"
    for (tid, fname) in rows:
     text_list += f"- {fname} (ID={tid})\n"
    await message.answer(text_list)

###############################################################################
# Группы (суперадмин)
###############################################################################
class GroupCreateFSM(StatesGroup):
    waiting_for_name = State()


@dp.message(lambda msg: msg.text == "Создать группу")
async def create_group_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
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

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO groups (name, created_at, created_by)
            VALUES (?, ?, ?)
        """, (name, datetime.datetime.now().isoformat(), message.from_user.id))
        conn.commit()
        await message.answer(f"Группа создана: {name}", reply_markup=admin_menu)
    except sqlite3.IntegrityError:
        await message.answer("Такая группа уже существует.", reply_markup=admin_menu)
    finally:
        conn.close()

    await state.clear()


@dp.message(lambda msg: msg.text == "Список групп")
async def list_groups(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    groups = list_all_groups()
    if not groups:
        await message.answer("Группы не найдены.")
        return

    text = "Группы:\n" + "\n".join([f"- {name} (ID={gid})" for gid, name in groups])
    await message.answer(text)


class GroupAdminAssignFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@dp.message(lambda msg: msg.text == "Назначить админа группы")
async def assign_group_admin_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    groups = list_all_groups()
    if not groups:
        await message.answer("Группы не найдены.")
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите группу:", reply_markup=cancel_kb)

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"ga_group:{gid}")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Группа для назначения админа:", reply_markup=inline_kb)
    await state.set_state(GroupAdminAssignFSM.waiting_for_group)


@dp.callback_query(lambda c: c.data.startswith("ga_group:"), GroupAdminAssignFSM.waiting_for_group)
async def assign_group_admin_pick_group(cb: CallbackQuery, state: FSMContext):
    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer("Некорректная группа.", show_alert=True)
        return

    await state.update_data(group_id=group_id)

    users = get_approved_users()
    if not users:
        await cb.message.answer("Нет одобренных пользователей.")
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
    await cb.message.answer("Выберите пользователя:", reply_markup=inline_kb)
    await state.set_state(GroupAdminAssignFSM.waiting_for_user)
    await cb.answer()


@dp.callback_query(lambda c: c.data.startswith("ga_user:"), GroupAdminAssignFSM.waiting_for_user)
async def assign_group_admin_pick_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await cb.answer("Группа не выбрана.", show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer("Некорректный пользователь.", show_alert=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT role
        FROM group_memberships
        WHERE user_id=? AND group_id=?
    """, (user_id, group_id))
    row = cur.fetchone()

    if row:
        if row[0] == "admin":
            msg = "Пользователь уже админ этой группы."
        else:
            cur.execute("""
                UPDATE group_memberships
                SET role='admin'
                WHERE user_id=? AND group_id=?
            """, (user_id, group_id))
            conn.commit()
            msg = "Роль пользователя обновлена на админа группы."
            try:
                group_name = get_group_name(group_id) or f"ID={group_id}"
                await bot.send_message(
                    user_id,
                    f"Вам назначена роль администратора группы: {group_name}."
                )
            except:
                pass
    else:
        cur.execute("""
            INSERT INTO group_memberships (user_id, group_id, role, created_at, created_by)
            VALUES (?, ?, 'admin', ?, ?)
        """, (user_id, group_id, datetime.datetime.now().isoformat(), cb.from_user.id))
        conn.commit()
        msg = "Пользователь назначен админом группы."
        try:
            group_name = get_group_name(group_id) or f"ID={group_id}"
            await bot.send_message(
                user_id,
                f"Вы добавлены в группу {group_name} как администратор."
            )
        except:
            pass

    conn.close()
    await cb.message.answer(msg, reply_markup=admin_menu)
    await cb.answer()
    await state.clear()


class GroupAddUserFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@dp.message(lambda msg: msg.text == "Добавить пользователя в группу")
async def add_user_to_group_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    groups = list_all_groups()
    if not groups:
        await message.answer("Группы не найдены.")
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите группу:", reply_markup=cancel_kb)

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
        await cb.answer("Некорректная группа.", show_alert=True)
        return

    await state.update_data(group_id=group_id)

    users = get_approved_users()
    if not users:
        await cb.message.answer("Нет одобренных пользователей.")
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
    await cb.message.answer("Выберите пользователя:", reply_markup=inline_kb)
    await state.set_state(GroupAddUserFSM.waiting_for_user)
    await cb.answer()


@dp.callback_query(lambda c: c.data.startswith("gm_user:"), GroupAddUserFSM.waiting_for_user)
async def add_user_to_group_pick_user(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await cb.answer("Группа не выбрана.", show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer("Некорректный пользователь.", show_alert=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT role
        FROM group_memberships
        WHERE user_id=? AND group_id=?
    """, (user_id, group_id))
    row = cur.fetchone()

    if row:
        if row[0] == "admin":
            msg = "Пользователь уже админ этой группы."
        else:
            msg = "Пользователь уже состоит в группе."
    else:
        cur.execute("""
            INSERT INTO group_memberships (user_id, group_id, role, created_at, created_by)
            VALUES (?, ?, 'member', ?, ?)
        """, (user_id, group_id, datetime.datetime.now().isoformat(), cb.from_user.id))
        conn.commit()
        msg = "Пользователь добавлен в группу."
        try:
            group_name = get_group_name(group_id) or f"ID={group_id}"
            await bot.send_message(
                user_id,
                f"Вы добавлены в группу {group_name}."
            )
        except:
            pass

    conn.close()
    await cb.message.answer(msg, reply_markup=admin_menu)
    await cb.answer()
    await state.clear()


class GroupRemoveUserFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_user = State()


@dp.message(lambda msg: msg.text == "Удалить пользователя из группы")
async def remove_user_from_group_start(message: types.Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    groups = list_all_groups()
    if not groups:
        await message.answer("Группы не найдены.")
        return

    await state.clear()
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите группу:", reply_markup=cancel_kb)

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
        await cb.answer("Некорректная группа.", show_alert=True)
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
        await cb.answer("Группа не выбрана.", show_alert=True)
        await state.clear()
        return

    try:
        user_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer("Некорректный пользователь.", show_alert=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM group_memberships
        WHERE user_id=? AND group_id=?
    """, (user_id, group_id))
    deleted = cur.rowcount > 0
    cur.execute("""
        UPDATE users
        SET last_group_id=NULL
        WHERE telegram_id=? AND last_group_id=?
    """, (user_id, group_id))
    conn.commit()
    conn.close()

    if not deleted:
        await cb.message.answer("Пользователь не найден в группе.", reply_markup=admin_menu)
        await cb.answer()
        await state.clear()
        return

    group_name = get_group_name(group_id) or f"ID={group_id}"
    await cb.message.answer(f"Пользователь удалён из группы {group_name}.", reply_markup=admin_menu)
    try:
        await bot.send_message(
            user_id,
            f"Вы удалены из группы {group_name}."
        )
    except:
        pass
    await cb.answer()
    await state.clear()


###############################################################################
# Заявки в группу (админ группы / суперадмин)
###############################################################################
@dp.message(lambda msg: msg.text == "Заявки в группу")
async def show_group_requests(message: types.Message):
    user_id = message.from_user.id
    if not is_superadmin(user_id) and not user_is_group_admin_any(user_id):
        await message.answer("Нет прав.")
        return

    group_id = None
    if not is_superadmin(user_id):
        group_id = get_last_group_id(user_id)
        if not group_id:
            await message.answer("Сначала выберите рабочую группу (кнопка «Сменить группу»).")
            return
        if not is_group_admin(user_id, group_id):
            await message.answer("Нет прав.")
            return
    else:
        group_id = get_last_group_id(user_id)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if group_id:
        cur.execute("""
            SELECT gr.id, gr.user_id, u.fullname, u.username, g.id, g.name, gr.type
            FROM group_requests gr
            JOIN users u ON u.telegram_id = gr.user_id
            JOIN groups g ON g.id = gr.group_id
            WHERE gr.status='pending' AND gr.group_id=?
            ORDER BY u.fullname
        """, (group_id,))
    else:
        cur.execute("""
            SELECT gr.id, gr.user_id, u.fullname, u.username, g.id, g.name, gr.type
            FROM group_requests gr
            JOIN users u ON u.telegram_id = gr.user_id
            JOIN groups g ON g.id = gr.group_id
            WHERE gr.status='pending'
            ORDER BY g.name, u.fullname
        """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет заявок в группу.")
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
        await cb.answer("Некорректная заявка.", show_alert=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, group_id, type, status
        FROM group_requests
        WHERE id=?
    """, (req_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        await cb.answer("Заявка не найдена.", show_alert=True)
        return

    req_user_id, group_id, req_type, status = row
    if status != "pending":
        conn.close()
        await cb.answer("Заявка уже обработана.", show_alert=True)
        return

    if not is_superadmin(user_id) and not is_group_admin(user_id, group_id):
        conn.close()
        await cb.answer("Нет прав!", show_alert=True)
        return

    group_name = get_group_name(group_id) or f"ID={group_id}"
    now = datetime.datetime.now().isoformat()

    if action == "grp_req_approve":
        if req_type == "join":
            if not user_in_group(req_user_id, group_id):
                cur.execute("""
                    INSERT INTO group_memberships (user_id, group_id, role, created_at, created_by)
                    VALUES (?, ?, 'member', ?, ?)
                """, (req_user_id, group_id, now, user_id))
        elif req_type == "leave":
            cur.execute("""
                DELETE FROM group_memberships
                WHERE user_id=? AND group_id=?
            """, (req_user_id, group_id))
            cur.execute("""
                UPDATE users
                SET last_group_id=NULL
                WHERE telegram_id=? AND last_group_id=?
            """, (req_user_id, group_id))

        cur.execute("""
            UPDATE group_requests
            SET status='approved', reviewed_at=?, reviewed_by=?
            WHERE id=?
        """, (now, user_id, req_id))
        conn.commit()
        conn.close()

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
    cur.execute("""
        UPDATE group_requests
        SET status='declined', reviewed_at=?, reviewed_by=?
        WHERE id=?
    """, (now, user_id, req_id))
    conn.commit()
    conn.close()

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

    admin_groups = [
        (gid, name) for (gid, name, role) in get_user_groups(user_id) if role == "admin"
    ]

    if not is_superadmin(user_id) and not admin_groups:
        await message.answer("Нет прав.")
        return

    if is_superadmin(user_id):
        groups = list_all_groups()
        allow_global = True
    else:
        groups = [(gid, name) for (gid, name) in admin_groups]
        allow_global = False

    if not groups and not allow_global:
        await message.answer("Группы не найдены.")
        return

    kb_rows = []
    for gid, name in groups:
        kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"set_group:{gid}")])

    if allow_global:
        kb_rows.append([InlineKeyboardButton(text="Глобально", callback_data="set_group:global")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите рабочую группу:", reply_markup=inline_kb)


@dp.callback_query(lambda c: c.data.startswith("set_group:"))
async def set_work_group(cb: CallbackQuery):
    user_id = cb.from_user.id
    payload = cb.data.split(":", 1)[1]

    if payload == "global":
        if not is_superadmin(user_id):
            await cb.answer("Нет прав!", show_alert=True)
            return
        set_last_group_id(user_id, None)
        await cb.message.answer("Рабочая группа сброшена. Режим: глобально.")
        await cb.answer()
        return

    try:
        group_id = int(payload)
    except ValueError:
        await cb.answer("Некорректная группа.", show_alert=True)
        return

    if not is_superadmin(user_id) and not is_group_admin(user_id, group_id):
        await cb.answer("Нет прав!", show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer("Группа не найдена.", show_alert=True)
        return

    if not set_last_group_id(user_id, group_id):
        await cb.answer("Пользователь не найден.", show_alert=True)
        return

    await cb.message.answer(f"Рабочая группа установлена: {group_name}")
    await cb.answer()

###############################################################################
# Назначить админом /make_admin, Отозвать админа /revoke_admin, Список админов
###############################################################################
@dp.message(lambda msg: msg.text == "Назначить админом")
async def pick_user_for_admin(message: types.Message):
    """
    Шаг 1: админ нажимает "Назначить админом".
    Бот показывает список одобренных, но не админов (is_approved=1, is_admin=0).
    """
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_id, fullname
        FROM users
        WHERE is_approved=1
            AND is_admin=0
        ORDER BY fullname
    """)
    rows = cur.fetchall()
    conn.close()

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
        await cb.answer("Нет прав!", show_alert=True)
        return

    user_id_str = cb.data.split(":")[1]
    user_id = int(user_id_str)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Одобряем + is_admin=1
    cur.execute("UPDATE users SET is_approved=1, is_admin=1 WHERE telegram_id=?", (user_id,))
    conn.commit()
    conn.close()

    await cb.message.answer(f"Пользователь {get_user_fullname(user_id)} теперь администратор.")
    log_action(cb.from_user.id, f"make_admin {user_id}")

    # Уведомим
    try:
        await bot.send_message(user_id, "Вам назначены права администратора!", reply_markup=admin_menu)
    except:
        pass

    await cb.answer()

@dp.message(lambda msg: msg.text == "Отозвать админа")
async def pick_admin_to_revoke(message: types.Message):
    """
    Шаг 1: админ нажимает "Отозвать админа".
    Бот показывает список пользователей, у которых is_admin=1 (кроме себя, если хотите).
    """
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Можем исключить из списка самого себя, если хотите
    cur.execute("""
        SELECT telegram_id, fullname
        FROM users
        WHERE is_admin=1
        AND telegram_id != ?
        ORDER BY fullname
    """, (message.from_user.id,))
    rows = cur.fetchall()
    conn.close()

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
        await cb.answer("Нет прав!", show_alert=True)
        return

    user_id_str = cb.data.split(":")[1]
    user_id = int(user_id_str)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin=0 WHERE telegram_id=?", (user_id,))
    conn.commit()
    conn.close()

    await cb.message.answer(f"Админ-права у {get_user_fullname(user_id)} отозваны.")
    log_action(cb.from_user.id, f"revoke_admin {user_id}")

    try:
        await bot.send_message(user_id, "У вас отозвали права администратора.")
    except:
        pass

    await cb.answer()

@dp.message(lambda msg: msg.text == "Список админов")
async def list_admins_cmd(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_admin=1")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет администраторов.")
        return

    txt = "Список админов:\n"
    for (tid,) in rows:
        txt += f"- {get_user_fullname(tid)}\n"
    await message.answer(txt)

###############################################################################
# Удалить сотрудника (целиком)
###############################################################################
@dp.message(lambda msg: msg.text == "Удалить сотрудника")
async def remove_user_prompt(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return

    # NEW: кнопка «Отмена»
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы удаляете сотрудника.\nЕсли передумали, нажмите «Отмена».",
        reply_markup=cancel_kb
    )

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_id, fullname
        FROM users
        WHERE is_approved=1
        AND is_admin=0
        ORDER BY fullname
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет (не админ) сотрудников для удаления.")
        return

    kb_rows = []
    for (tid, fname) in rows:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"remove_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите сотрудника для удаления:", reply_markup=inline_kb)

@dp.callback_query(lambda c: c.data.startswith("remove_user:"))
async def callback_remove_user(cb: CallbackQuery):
    if not is_user_admin(cb.from_user.id):
        await cb.answer("Нет прав!", show_alert=True)
        return

    user_id = int(cb.data.split(":")[1])

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM absences WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM users WHERE telegram_id=?", (user_id,))
    conn.commit()
    conn.close()

    await cb.message.answer(f"Сотрудник {user_id} удалён.")
    log_action(cb.from_user.id, f"remove_user {user_id}")
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
        await message.answer("Вы не зарегистрированы.")
        return
    if not is_user_approved(message.from_user.id):
        await message.answer("Ваш аккаунт не одобрен.")
        return
    if not is_superadmin(message.from_user.id) and not user_has_any_group(message.from_user.id):
        await message.answer("Вы не состоите ни в одной группе. Подайте заявку на вступление.")
        return

    # 1) Создадим Reply-клавиатуру с кнопкой «Отмена»
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отмена")]
        ],
        resize_keyboard=True
    )

    # 2) Сообщим пользователю, что можно прервать действие
    await message.answer(
        "Сейчас вы добавляете отсутствие.\n"
        "Если ошиблись, нажмите «Отмена», чтобы прервать.",
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
        "Выберите категорию отсутствия:",
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
        await message.answer("Некорректная дата. Формат: дд.мм.гггг.")
        return

    await state.update_data(start_date=str(date_obj))
    await message.answer("Введите дату окончания (дд.мм.гггг):")
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
        await message.answer("Дата окончания не может быть раньше даты начала.")
        return

    await state.update_data(end_date=str(date_obj))
    await message.answer("Введите комментарий (или '-' если без комментария):")
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

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO absences (user_id, category, start_date, end_date, comment, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, cat, sd, ed, comment, "pending"))
    abs_id = cur.lastrowid
    conn.commit()
    conn.close()

    await message.answer(
        f"Заявка #{abs_id} на отсутствие '{cat}' с {sd} по {ed}\n"
        f"Комментарий: {comment or '—'}\nОтправлена на рассмотрение."
    )
    log_action(user_id, f"Requested absence {abs_id}: {cat} {sd}-{ed}")

    # Уведомим админов
    for admin_id in get_admins():
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"approve_abs:{abs_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"decline_abs:{abs_id}")
            ]
        ])
        text_admin = (
            f"{get_user_fullname(user_id)} добавил заявку #{abs_id}:\n"
            f"{cat} {sd}–{ed}\n"
            f"Комментарий: {comment or '—'} (pending)"
        )
        try:
            await bot.send_message(admin_id, text_admin, reply_markup=kb)
        except:
            pass

    if is_user_admin(message.from_user.id):
        await message.answer(
            "Отсутствие успешно добавлено! Возвращаю вас в админ-меню.",
            reply_markup=admin_menu
        )
    else:
        await message.answer(
            "Отсутствие успешно добавлено! Возвращаю вас в пользовательское меню.",
            reply_markup=user_menu
        )

    await state.clear()

###############################################################################
# "Мои отсутствия" + "Удалить мои отсутствия"
###############################################################################
class EditAbsenceFSM(StatesGroup):
    waiting_for_new_category = State()
    waiting_for_new_start_date = State()
    waiting_for_new_end_date = State()
    waiting_for_new_comment = State()

@dp.message(lambda msg: msg.text == "Мои отсутствия")
async def show_my_absences(message: types.Message):
    user_id = message.from_user.id
    if not is_user_approved(user_id):
        await message.answer("Вы не одобрены.")
        return
    if not is_superadmin(user_id) and not user_has_any_group(user_id):
        await message.answer("Вы не состоите ни в одной группе. Подайте заявку на вступление.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, category, start_date, end_date, comment, status
        FROM absences
        WHERE user_id=?
        ORDER BY start_date
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("У вас нет заявок на отсутствие.")
        return

    lines = []
    kb_rows = []
    for (abs_id, cat, sd, ed, cmnt, st) in rows:
        line = f"#{abs_id} — {cat}, {sd}–{ed}, статус={st}, коммент: {cmnt or '—'}"
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
        await message.answer("Вы не зарегистрированы.")
        return

    groups = get_user_groups(user_id)
    if not groups:
        await message.answer("Вы пока не состоите ни в одной группе.")
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
        await message.answer("Вы не зарегистрированы.")
        return
    if not is_user_approved(user_id):
        await message.answer("Ваш аккаунт не одобрен.")
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
        await cb.answer("Ваш аккаунт не одобрен.", show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer("Некорректная группа.", show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer("Группа не найдена.", show_alert=True)
        return

    if user_in_group(user_id, group_id):
        await cb.answer("Вы уже состоите в этой группе.", show_alert=True)
        return

    if has_pending_group_request(user_id, group_id, "join"):
        await cb.answer("Заявка уже отправлена и ожидает решения.", show_alert=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO group_requests (user_id, group_id, type, status, requested_at, requested_by)
        VALUES (?, ?, 'join', 'pending', ?, ?)
    """, (user_id, group_id, datetime.datetime.now().isoformat(), user_id))
    req_id = cur.lastrowid
    conn.commit()
    conn.close()

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
        await message.answer("Вы не зарегистрированы.")
        return
    if not is_user_approved(user_id):
        await message.answer("Ваш аккаунт не одобрен.")
        return

    groups = get_user_groups(user_id)
    if not groups:
        await message.answer("Вы пока не состоите ни в одной группе.")
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
        await cb.answer("Ваш аккаунт не одобрен.", show_alert=True)
        return

    try:
        group_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer("Некорректная группа.", show_alert=True)
        return

    group_name = get_group_name(group_id)
    if not group_name:
        await cb.answer("Группа не найдена.", show_alert=True)
        return

    if not user_in_group(user_id, group_id):
        await cb.answer("Вы не состоите в этой группе.", show_alert=True)
        return

    if has_pending_group_request(user_id, group_id, "leave"):
        await cb.answer("Заявка уже отправлена и ожидает решения.", show_alert=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO group_requests (user_id, group_id, type, status, requested_at, requested_by)
        VALUES (?, ?, 'leave', 'pending', ?, ?)
    """, (user_id, group_id, datetime.datetime.now().isoformat(), user_id))
    req_id = cur.lastrowid
    conn.commit()
    conn.close()

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

@dp.message(lambda msg: msg.text == "Удалить мои отсутствия")
async def admin_delete_my_absences(message: types.Message):
    """
    Аналог "Мои отсутствия", но просто другая надпись в меню
    """
    await show_my_absences(message)

###############################################################################
# Запрос на удаление одобренного отсутствия
###############################################################################
@dp.callback_query(lambda c: c.data.startswith("request_del:"))
async def request_delete_absence(cb: CallbackQuery):
    abs_id = int(cb.data.split(":")[1])

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, category, start_date, end_date, status
        FROM absences
        WHERE id=?
    """, (abs_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await cb.answer("Отсутствие не найдено.", show_alert=True)
        return

    user_id, cat, sd, ed, st = row
    if user_id != cb.from_user.id:
        await cb.answer("Это не ваша заявка!", show_alert=True)
        return
    if st != "approved":
        await cb.answer("Удалять можно только 'approved'.", show_alert=True)
        return

    # Отправим запрос админам
    for admin_id in get_admins():
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить удаление", callback_data=f"approve_del:{abs_id}"),
                InlineKeyboardButton(text="Отклонить удаление", callback_data=f"decline_del:{abs_id}")
            ]
        ])
        txt = (
            f"{get_user_fullname(cb.from_user.id)} просит удалить "
            f"заявку #{abs_id} ({cat} {sd}–{ed}, status={st})."
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
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, category, start_date, end_date, comment, status
        FROM absences
        WHERE id=?
    """, (abs_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await cb.answer("Заявка не найдена.", show_alert=True)
        return

    user_id, cat, sd, ed, cmnt, st = row
    if user_id != cb.from_user.id:
        await cb.answer("Это не ваша заявка!", show_alert=True)
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
    await cb.message.answer("Введите новую дату начала (дд.мм.гггг):")
    await state.set_state(EditAbsenceFSM.waiting_for_new_start_date)
    await cb.answer()

@dp.message(EditAbsenceFSM.waiting_for_new_start_date)
async def edit_absence_start_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Формат: дд.мм.гггг.")
        return

    await state.update_data(new_start_date=str(date_obj))
    await message.answer("Введите новую дату окончания (дд.мм.гггг):")
    await state.set_state(EditAbsenceFSM.waiting_for_new_end_date)

@dp.message(EditAbsenceFSM.waiting_for_new_end_date)
async def edit_absence_end_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Формат: дд.мм.гггг.")
        return

    data = await state.get_data()
    start_str = data["new_start_date"]
    start_date_obj = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
    if date_obj < start_date_obj:
        await message.answer("Дата окончания не может быть раньше даты начала.")
        return

    await state.update_data(new_end_date=str(date_obj))
    await message.answer("Введите новый комментарий (или '-' если без комментария):")
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
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT category, start_date, end_date, comment
        FROM absences
        WHERE id=?
    """, (abs_id,))
    old_row = cur.fetchone()
    if not old_row:
        await message.answer("Исходная заявка не найдена.")
        conn.close()
        return

    old_cat, old_sd, old_ed, old_cmnt = old_row

    # 2) Записываем в edit_requests
    cur.execute("""
        INSERT INTO edit_requests (abs_id, new_cat, new_sd, new_ed, new_comment, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (abs_id, new_cat, new_sd, new_ed, comment, user_id))
    req_id = cur.lastrowid
    conn.commit()

    # 3) Формируем уведомление админу: "старое" vs "новое"
    old_part = (
        f"Старое:\n"
        f"Категория: {old_cat}\n"
        f"Даты: {old_sd}–{old_ed}\n"
        f"Комментарий: {old_cmnt or '—'}\n\n"
    )
    new_part = (
        f"Новое:\n"
        f"Категория: {new_cat}\n"
        f"Даты: {new_sd}–{new_ed}\n"
        f"Комментарий: {comment or '—'}\n\n"
        f"(pending)"
    )
    text_admin = (
        f"Пользователь {get_user_fullname(user_id)} хочет изменить заявку #{abs_id}.\n\n"
        f"{old_part}{new_part}"
    )

    # 4) Закрываем conn
    conn.close()

    # 5) Сообщаем пользователю
    await message.answer(
        f"Запрос на изменение заявки #{abs_id} отправлен на одобрение администратору.\n"
        f"(Старое и новое видно админу)."
    )

    # 6) Шлём админам
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Одобрить", callback_data=f"approve_edit:{req_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"decline_edit:{req_id}")
    ]])
    for admin_id in get_admins():
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
    if not is_user_admin(cb.from_user.id):
        await cb.answer("Нет прав админа!", show_alert=True)
        return

    action, req_id_str = cb.data.split(":")
    req_id = int(req_id_str)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT abs_id, new_cat, new_sd, new_ed, new_comment, user_id FROM edit_requests WHERE id=?", (req_id,))
    row = cur.fetchone()
    if not row:
        await cb.message.answer("Запрос на изменение не найден.")
        conn.close()
        await cb.answer()
        return

    abs_id, new_cat, new_sd, new_ed, new_comment, user_id = row

    # Считываем старые поля (если хотите показать «старое → новое» админу)
    cur.execute("""
        SELECT category, start_date, end_date, comment
        FROM absences
        WHERE id=?
    """, (abs_id,))
    old_row = cur.fetchone()
    if not old_row:
        await cb.message.answer("Исходная заявка не найдена.")
        conn.close()
        await cb.answer()
        return
    old_cat, old_sd, old_ed, old_cmnt = old_row

    if action == "approve_edit":
        # Применяем новые поля
        cur.execute("""
            UPDATE absences
            SET category=?, start_date=?, end_date=?, comment=?
            WHERE id=?
        """, (new_cat, new_sd, new_ed, new_comment, abs_id))

        # Удаляем запрос
        cur.execute("DELETE FROM edit_requests WHERE id=?", (req_id,))
        conn.commit()
        conn.close()

        # Показываем «старое → новое» админу (при желании)
        old_text = (
            f"Старое:\nКатегория: {old_cat}\n"
            f"Даты: {old_sd}–{old_ed}\n"
            f"Комментарий: {old_cmnt or '—'}"
        )
        new_text = (
            f"Новое:\nКатегория: {new_cat}\n"
            f"Даты: {new_sd}–{new_ed}\n"
            f"Комментарий: {new_comment or '—'}"
        )
        summary = f"Изменение заявки #{abs_id} одобрено.\n\n{old_text}\n\n→ {new_text}"
        await cb.message.answer(summary)

        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"Ваше изменение заявки #{abs_id} одобрено!\n"
                f"Теперь: {new_cat}, {new_sd}–{new_ed}, {new_comment or '—'}"
            )
        except:
            pass

        await cb.answer()

    else:  # "decline_edit"
        # Никакого UPDATE не делаем — просто удаляем запрос
        cur.execute("DELETE FROM edit_requests WHERE id=?", (req_id,))
        conn.commit()
        conn.close()

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
    if not is_user_admin(cb.from_user.id):
        await cb.answer("Нет прав!", show_alert=True)
        return

    action, abs_id_str = cb.data.split(":")
    abs_id = int(abs_id_str)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, category, start_date, end_date
        FROM absences
        WHERE id=? AND status='approved'
    """, (abs_id,))
    row = cur.fetchone()
    if not row:
        await cb.message.answer("Не найдено или не 'approved'.")
        conn.close()
        await cb.answer()
        return

    user_id, cat, sd, ed = row
    if action == "approve_del":
        cur.execute("DELETE FROM absences WHERE id=?", (abs_id,))
        conn.commit()
        conn.close()
        await cb.message.answer(f"Удаление #{abs_id} одобрено. Запись удалена.")
        log_action(cb.from_user.id, f"approve_del absence {abs_id}")
        try:
            await bot.send_message(user_id, f"Админ удалил вашу заявку #{abs_id}.")
        except:
            pass
    else:
        conn.close()
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
@dp.message(lambda msg: msg.text == "Заявки на отсутствие")
async def show_absence_requests(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав админа.")
        return

    # Cancel KB
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы удаляете отсутствие конкретного сотрудника.\n"
        "Если передумали, нажмите «Отмена».",
        reply_markup=cancel_kb
    )

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.user_id, a.category, a.start_date, a.end_date, a.comment
        FROM absences a
        JOIN users u ON a.user_id=u.telegram_id
        WHERE a.status='pending'
        ORDER BY a.start_date
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет заявок (pending).")
        return

    for row in rows:
        abs_id, uid, cat, sd, ed, cmnt = row
        user_disp = get_user_fullname(uid)
        text_info = (
            f"Заявка #{abs_id}\n"
            f"От: {user_disp}\n"
            f"Категория: {cat}\n"
            f"Период: {sd}–{ed}\n"
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
    if not is_user_admin(cb.from_user.id):
        await cb.answer("Нет прав!", show_alert=True)
        return

    action, abs_id_str = cb.data.split(":")
    abs_id = int(abs_id_str)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, category, start_date, end_date, comment, status
        FROM absences
        WHERE id=?
    """, (abs_id,))
    row = cur.fetchone()
    if not row:
        await cb.answer("Заявка не найдена.", show_alert=True)
        conn.close()
        return

    user_id, cat, sd, ed, cmnt, st = row
    if st != "pending":
        await cb.answer("Эта заявка уже обработана.", show_alert=True)
        conn.close()
        return

    if action == "approve_abs":
        new_status = "approved"
        txt_admin = f"Заявка #{abs_id} одобрена."
        txt_user = f"Ваша заявка #{abs_id} ({cat} {sd}–{ed}) одобрена!"
    else:
        new_status = "declined"
        txt_admin = f"Заявка #{abs_id} отклонена."
        txt_user = f"Ваша заявка #{abs_id} ({cat} {sd}–{ed}) отклонена."

    cur.execute("UPDATE absences SET status=? WHERE id=?", (new_status, abs_id))
    conn.commit()
    conn.close()

    await cb.message.answer(txt_admin)
    log_action(cb.from_user.id, f"{action} absence {abs_id}")

    try:
        await bot.send_message(user_id, txt_user)
    except:
        pass

    await cb.answer()

###############################################################################
# Посмотреть отсутствия сотрудника (админ)
###############################################################################
@dp.message(lambda msg: msg.text == "Посмотреть отсутствия сотрудника")
async def select_user_for_absences(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав админа.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_id, fullname
        FROM users
        WHERE is_approved=1
        ORDER BY fullname
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет одобренных сотрудников.")
        return

    kb_rows = []
    for (tid, fname) in rows:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"show_abs:{tid}")
        ])
         
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите сотрудника:", reply_markup=inline_kb)

@dp.callback_query(lambda c: c.data.startswith("show_abs:"))
async def cb_show_absences(cb: CallbackQuery):
    if not is_user_admin(cb.from_user.id):
        await cb.answer("Нет прав!", show_alert=True)
        return

    user_id = int(cb.data.split(":")[1])
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT category, start_date, end_date, comment, status
        FROM absences
        WHERE user_id=?
        ORDER BY start_date
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    user_disp = get_user_fullname(user_id)

    if not rows:
        await cb.message.answer(f"У {user_disp} нет заявок.")
        await cb.answer()
        return

    text_report = f"Отсутствия {user_disp}:\n"
    for (cat, sd, ed, cmnt, st) in rows:
        text_report += f"- {cat} {sd}–{ed}, [{st}], {cmnt or '—'}\n"

    await cb.message.answer(text_report)
    await cb.answer()

###############################################################################
# Удалить отсутствие сотрудника (админ)
###############################################################################
@dp.message(lambda msg: msg.text == "Удалить отсутствие сотрудника")
async def admin_delete_absence_start(message: types.Message):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав админа.")
        return

    # NEW
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы удаляете отсутствие сотрудника.\nЕсли передумали, нажмите «Отмена».",
        reply_markup=cancel_kb
    )

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_id, fullname
        FROM users
        WHERE is_approved=1
        ORDER BY fullname
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет одобренных сотрудников.")
        return

    kb_rows = []
    for (tid, fname) in rows:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"adm_del_pickuser:{tid}")
        ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("Выберите сотрудника, у которого хотите удалить конкретное отсутствие:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("adm_del_pickuser:"))
async def admin_delete_absences_pickuser(cb: CallbackQuery):
    if not is_user_admin(cb.from_user.id):
        await cb.answer("Нет прав!", show_alert=True)
        return

    user_id = int(cb.data.split(":")[1])
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, category, start_date, end_date, comment, status
        FROM absences
        WHERE user_id=?
        ORDER BY start_date
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    user_disp = get_user_fullname(user_id)

    if not rows:
        await cb.message.answer(f"У {user_disp} нет заявок.")
        await cb.answer()
        return

    text_rep = f"Отсутствия {user_disp}:\n"
    kb_rows = []
    for (abs_id, cat, sd, ed, cmnt, st) in rows:
        text_rep += f"#{abs_id} {cat} {sd}–{ed}, [{st}], {cmnt or '—'}\n"
        kb_rows.append([InlineKeyboardButton(
            text=f"Удалить #{abs_id}",
            callback_data=f"adm_del_abs:{abs_id}"
        )])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer(text_rep + "\nНажмите «Удалить #ID» для удаления.", reply_markup=inline_kb)
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("adm_del_abs:"))
async def admin_delete_absence_final(cb: CallbackQuery):
    if not is_user_admin(cb.from_user.id):
        await cb.answer("Нет прав!", show_alert=True)
        return

    abs_id = int(cb.data.split(":")[1])

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id, category, start_date, end_date FROM absences WHERE id=?", (abs_id,))
    row = cur.fetchone()
    if not row:
        await cb.answer("Не найдено или уже удалено.", show_alert=True)
        conn.close()
        return

    user_id, cat, sd, ed = row
    cur.execute("DELETE FROM absences WHERE id=?", (abs_id,))
    conn.commit()
    conn.close()

    await cb.message.answer(f"Отсутствие #{abs_id} ({cat} {sd}–{ed}) удалено админом.")
    log_action(cb.from_user.id, f"adm_del_abs {abs_id}")

    try:
        await bot.send_message(user_id, f"Админ удалил ваше отсутствие #{abs_id} ({cat} {sd}–{ed}).")
    except:
        pass

    await cb.answer()

###############################################################################
# ВЫГРУЗКА CSV ЗА ПЕРИОД
###############################################################################
class CsvExportFSM(StatesGroup):
    waiting_for_start_date = State()
    waiting_for_end_date = State()

@dp.message(lambda msg: msg.text == "Выгрузить отсутствия (CSV)")
async def start_csv_export(message: types.Message, state: FSMContext):
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав админа.")
        return

    await state.clear()  # optional if you want to ensure no leftover states

    # NEW: create "Cancel" reply keyboard
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы собираетесь выгрузить отсутствия (CSV).\n"
        "Введите дату начала периода (дд.мм.гггг) или нажмите «Отмена», чтобы прервать.",
        reply_markup=cancel_kb
    )

    await state.set_state(CsvExportFSM.waiting_for_start_date)

@dp.message(CsvExportFSM.waiting_for_start_date)
async def csv_export_start_date(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        if is_user_admin(message.from_user.id):
            await message.answer("Операция отменена. Возвращаю вас в меню администратора.", reply_markup=admin_menu)
        else:
            await message.answer("Операция отменена. Возвращаю вас в меню пользователя.", reply_markup=user_menu)
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
    if message.text == "Отмена":
        await state.clear()
        if is_user_admin(message.from_user.id):
            await message.answer("Операция отменена. Возвращаю вас в меню администратора.", reply_markup=admin_menu)
        else:
            await message.answer("Операция отменена. Возвращаю вас в меню пользователя.", reply_markup=user_menu)
        return

    text = message.text.strip()
    try:
        end_date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Введите в формате дд.мм.гггг, например 15.06.2025.")
        return  # Не сбрасываем state, даём ввести снова

    data = await state.get_data()
    start_date_str = data["start_date"]
    start_date_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()

    if end_date_obj < start_date_obj:
        await message.answer("Дата окончания не может быть раньше даты начала. Попробуйте снова.")
        return  # Не сбрасываем state, остаёмся в этом состоянии

    # теперь идёт твоя логика для формирования CSV...
    await state.update_data(end_date=str(end_date_obj))
    sds = str(start_date_obj)
    eds = str(end_date_obj)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Выбираем approved-отсутствия, пересекающие [sds; eds]
    cur.execute("""
        SELECT a.user_id, a.category, a.start_date, a.end_date, a.comment,
               u.fullname, u.username
        FROM absences a
        JOIN users u ON a.user_id = u.telegram_id
        WHERE a.status='approved'
          AND date(a.start_date) <= date(?)
          AND date(a.end_date) >= date(?)
        ORDER BY a.start_date
    """, (eds, sds))
    rows = cur.fetchall()
    conn.close()

    logging.debug(f"Found {len(rows)} rows for CSV export from {sds} to {eds}")

    if not rows:
        await message.answer(f"Нет 'approved' отсутствий в период {sds}–{eds}.")
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
        lines.append(f"{user_str};{uname or ''};{cat};{sd};{ed};{cmnt_esc}")

    logging.debug(f"CSV lines count (including header): {len(lines)}")

    csv_text = "\n".join(lines)
    from io import BytesIO
    from aiogram.types import BufferedInputFile
    bom = b'\xef\xbb\xbf'  # UTF-8 BOM
    csv_bytes = bom + csv_text.encode('utf-8')
    buf = BytesIO(csv_bytes)
    buf.seek(0)
    input_file = BufferedInputFile(buf.getvalue(), filename=f"absences_{sds}_{eds}.csv")

    await message.answer_document(document=input_file, caption="CSV-выгрузка.")

    log_action(message.from_user.id, f"Export CSV {sds}-{eds}")
    await message.answer(
        "Выгрузка завершена! Возвращаю вас в админ-меню.",
        reply_markup=admin_menu
    )

    await state.clear()

###################################
# ВЫГРУЗКА ОТСУТСТВИЙ ЗА СЕГОДНЯ
######################################

@dp.message(lambda msg: msg.text == "Выгрузить отсутствия за сегодня")
async def show_absences_today(message: types.Message):
    """
    Показываем список одобренных отсутствий, которые пересекаются с 'сегодня'.
    """
    if not is_user_admin(message.from_user.id):
        await message.answer("Нет прав админа.")
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
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.user_id,
               a.category,
               a.start_date,
               a.end_date,
               a.comment,
               u.fullname,
               u.username
        FROM absences a
        JOIN users u ON a.user_id = u.telegram_id
        WHERE a.status='approved'
          AND date(a.start_date) <= date(:tod)
          AND date(a.end_date) >= date(:tod)
        ORDER BY a.start_date
    """, {"tod": today_iso})
    rows = cur.fetchall()
    conn.close()


    if not rows:
        await message.answer(f"На сегодня ({today_display}) нет одобренных отсутствий.")
        return

    # Формируем текст в формате "Фамилия И.О., причина, срок"
    lines = []
    for (uid, category, sd, ed, cmnt, fullname, username) in rows:
        
        # Преобразуем 'YYYY-MM-DD' -> 'дд.мм.гггг'
        start_disp = datetime.datetime.strptime(sd, "%Y-%m-%d").strftime("%d.%m.%Y")
        end_disp = datetime.datetime.strptime(ed, "%Y-%m-%d").strftime("%d.%m.%Y")
        
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
#FSM для "Добавить отсутствие другому сотруднику"
################################################
class AddAbsenceForAnotherFSM(StatesGroup):
    waiting_for_user = State()
    waiting_for_category = State()
    waiting_for_start_date = State()
    waiting_for_end_date = State()
    waiting_for_comment = State()


@dp.message(lambda msg: msg.text == "Добавить отсутствие другому сотруднику")
async def add_absence_for_another_start(message: types.Message, state: FSMContext):
    """
    1) Любой одобренный пользователь нажимает «Добавить отсутствие другому сотруднику».
    2) Бот показывает список одобренных пользователей (is_approved=1).
    """
    if not is_user_approved(message.from_user.id):
        await message.answer("Вы не одобрены, не можете добавлять отсутствие другим.")
        return
    if not is_superadmin(message.from_user.id) and not user_has_any_group(message.from_user.id):
        await message.answer("Вы не состоите ни в одной группе. Подайте заявку на вступление.")
        return

    # Сбросим текущее состояние, если вдруг пользователь был в другом процессе
    await state.clear()

    # NEW
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer(
        "Сейчас вы добавляете отсутствие другому сотруднику.\n"
        "Если передумали, нажмите «Отмена».",
        reply_markup=cancel_kb
    )

    # Собираем список одобренных сотрудников
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_id, fullname
        FROM users
        WHERE is_approved=1
        ORDER BY fullname
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет ни одного одобренного сотрудника в системе.")
        return

    # Формируем inline-кнопки для выбора сотрудника
    kb_rows = []
    for (tid, fname) in rows:
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
        await cb.answer("Ваш аккаунт не одобрен.")
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
    await cb.message.answer("Выберите категорию отсутствия:", reply_markup=kb)
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_category)
    await cb.message.answer(
        "Возвращаю вас в админ-меню.",
        reply_markup=admin_menu
    )
    await cb.answer()


@dp.callback_query(lambda c: c.data.startswith("another_cat_"), AddAbsenceForAnotherFSM.waiting_for_category)
async def pick_category_for_another(cb: CallbackQuery, state: FSMContext):
    """
    Сохраняем категорию, просим дату начала (дд.мм.гггг).
    """
    if not is_user_approved(cb.from_user.id):
        await cb.answer("Ваш аккаунт не одобрен.")
        return

    category = cb.data.split("another_cat_")[1]  # vacation / sick / dayoff / other
    await state.update_data(category=category)

    await cb.message.answer(
        f"Категория выбрана: {category}.\nВведите дату начала (дд.мм.гггг):"
    )
    await cb.message.answer(
        "Возвращаю вас в админ-меню.",
        reply_markup=admin_menu
    )
    await cb.answer()
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_start_date)


@dp.message(AddAbsenceForAnotherFSM.waiting_for_start_date)
async def another_absence_start_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Попробуйте снова (дд.мм.гггг).")
        return

    await state.update_data(start_date=str(date_obj))  # Сохраним как 'YYYY-MM-DD'
    await message.answer("Введите дату окончания (дд.мм.гггг):")
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_end_date)


@dp.message(AddAbsenceForAnotherFSM.waiting_for_end_date)
async def another_absence_end_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Некорректная дата. Попробуйте снова (дд.мм.гггг).")
        return

    data = await state.get_data()
    start_date_str = data["start_date"]
    start_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    if date_obj < start_obj:
        await message.answer("Дата окончания не может быть раньше даты начала.")
        return

    await state.update_data(end_date=str(date_obj))
    await message.answer("Введите комментарий (или '-' если без комментария):")
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

    # Можно задать статус='pending' или сразу 'approved', как хотите
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO absences (user_id, category, start_date, end_date, comment, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (target_user_id, category, sd, ed, comment, "pending"))
    abs_id = cur.lastrowid
    conn.commit()
    conn.close()

    await message.answer(
        f"Отсутствие #{abs_id} добавлено сотруднику {get_user_fullname(target_user_id)}.\n"
        f"Категория: {category}, {sd}–{ed}\nКомментарий: {comment or '—'}\nСтатус: pending."
    )
    log_action(message.from_user.id, f"AddAbsForAnother user={target_user_id}, abs_id={abs_id}")

    # При желании уведомляем самого сотрудника:
    try:
        await bot.send_message(
            target_user_id,
            f"Вам добавлено отсутствие #{abs_id} ({category}, {sd}–{ed}) от другого пользователя.\n"
            f"Комментарий: {comment or '—'}\n(статус: pending)"
        )
    except:
        pass

    # ──── ВАЖНО ────
    # Теперь сохраняем user_id: это тот, кто ИНИЦИИРОВАЛ добавление
    user_id = message.from_user.id

     # Уведомим админов
    for admin_id in get_admins():
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"approve_abs:{abs_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"decline_abs:{abs_id}")
            ]
        ])
        text_admin = (
            f"{get_user_fullname(user_id)} добавил заявку #{abs_id} "
            f"ДЛЯ {get_user_fullname(target_user_id)}:\n"
            f"{category} {sd}–{ed}\n"
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


#############################################
# Обновить меню
#############################################

async def broadcast_new_menu():
    """
    Рассылает новое меню всем одобренным пользователям.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Берём только одобренных (is_approved=1), т.к. не имеет смысла обновлять не одобренным
    cur.execute("SELECT telegram_id FROM users WHERE is_approved=1")
    rows = cur.fetchall()
    conn.close()

    updated_count = 0
    for (tg_id,) in rows:
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
        await message.answer("Нет прав админа.")
        return

    await broadcast_new_menu()
    await message.answer("Меню обновлено у всех одобренных пользователей.")

###############################################################################
# Fallback
###############################################################################
@dp.message()
async def fallback_handler(message: types.Message):
    tg_id = message.from_user.id
    if not user_exists_in_db(tg_id):
        await message.answer("Вы не зарегистрированы. Нажмите «Зарегистрироваться».", reply_markup=not_approved_menu)
        return
    if not is_user_approved(tg_id):
        await message.answer("Ваш аккаунт не одобрен. Нажмите «Зарегистрироваться».", reply_markup=not_approved_menu)
        return

    await message.answer("Неизвестная команда. Вот ваше меню:", reply_markup=get_role_menu(tg_id))

#######################
# Глобальный хендлер "Отмена" (Reply-кнопка)
###############################
@dp.message(StateFilter("*"), lambda msg: msg.text == "Отмена")
async def cancel_process(message: types.Message, state: FSMContext):
    """
    Если пользователь во время любого состояния FSM нажмёт «Отмена»,
    сбросим состояние и вернём ему меню.
    """
    await state.clear()

    await message.answer(
        "Операция отменена. Возвращаю вас в меню.",
        reply_markup=get_role_menu(message.from_user.id)
    )

###############################################################################
# Запуск
###############################################################################
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
