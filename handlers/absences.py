import datetime
import logging
from io import BytesIO

from aiogram import Bot, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile,
)

from core import get_admin_scope, get_role_menu, is_superadmin, user_has_any_group
from db_repo import (
    log_action,
    user_exists_in_db,
    is_user_approved,
    get_admins,
    get_user_groups,
    get_group_admins,
    get_group_members,
    get_approved_users,
    get_user_fullname,
    user_in_group,
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
)
from texts import (
    TEXT_NOT_REGISTERED_SHORT,
    TEXT_NOT_APPROVED_SHORT,
    TEXT_NOT_IN_ANY_GROUP,
    TEXT_CANCEL_BUTTON,
    TEXT_CANCEL_HINT_GENERIC,
    TEXT_CANCEL_HINT,
    TEXT_SELECT_ABSENCE_CATEGORY,
    TEXT_INVALID_DATE_FORMAT,
    TEXT_ENTER_END_DATE,
    TEXT_END_DATE_BEFORE_START,
    TEXT_ENTER_COMMENT,
    TEXT_SELECT_GROUP_FIRST,
    TEXT_NO_RIGHTS_ADMIN,
    TEXT_NO_RIGHTS_ADMIN_ALERT,
    TEXT_SELECT_USER,
    TEXT_NO_APPROVED_EMPLOYEES,
    TEXT_GROUP_NO_USERS,
    TEXT_INVALID_USER,
    TEXT_NOT_YOUR_REQUEST,
    TEXT_REQUEST_NOT_FOUND,
    TEXT_ENTER_NEW_START_DATE,
    TEXT_ENTER_NEW_END_DATE,
    TEXT_ENTER_NEW_COMMENT,
    TEXT_ORIGINAL_REQUEST_NOT_FOUND,
    TEXT_INVALID_REQUEST,
    TEXT_SELECT_GROUP_FIRST_ALERT,
    TEXT_BACK_TO_MENU,
    TEXT_INVALID_DATE_TRY_AGAIN,
    TEXT_ENTER_PERIOD_START_OR_CANCEL,
    TEXT_CANCELLED,
    TEXT_NO_RIGHTS_ALERT,
)
from utils import format_date_display

router = Router()
bot: Bot | None = None


def set_bot(bot_instance: Bot) -> None:
    global bot
    bot = bot_instance


###############################################################################
# FSM для добавления отсутствия
###############################################################################
class AbsenceRequestFSM(StatesGroup):
    waiting_for_category = State()
    waiting_for_start_date = State()
    waiting_for_end_date = State()
    waiting_for_comment = State()


@router.message(lambda msg: msg.text == "Добавить отсутствие")
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

    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXT_CANCEL_BUTTON)]
        ],
        resize_keyboard=True
    )

    await message.answer(
        f"Сейчас вы добавляете отсутствие.\n{TEXT_CANCEL_HINT_GENERIC}",
        reply_markup=cancel_kb
    )

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


@router.callback_query(lambda c: c.data.startswith("cat_"), AbsenceRequestFSM.waiting_for_category)
async def process_category_choice(cb: CallbackQuery, state: FSMContext):
    category = cb.data.split("cat_")[1]
    await state.update_data(category=category)
    await cb.message.answer(f"Вы выбрали {category}. Введите дату начала (дд.мм.гггг):")
    await state.set_state(AbsenceRequestFSM.waiting_for_start_date)
    await cb.answer()


@router.message(AbsenceRequestFSM.waiting_for_start_date)
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


@router.message(AbsenceRequestFSM.waiting_for_end_date)
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


@router.message(AbsenceRequestFSM.waiting_for_comment)
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
        except Exception:
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


@router.message(lambda msg: msg.text in {"Показать мои отсутствия", "Мои заявки"})
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
    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

    await message.answer(text_report, reply_markup=inline_kb)


@router.message(lambda msg: msg.text in {"Удалить мои отсутствия", "Удалить отсутствие"})
async def admin_delete_my_absences(message: types.Message):
    """
    Аналог "Показать мои отсутствия", но другая надпись в меню.
    """
    await show_my_absences(message)


@router.message(lambda msg: msg.text == "Изменить отсутствие")
async def admin_edit_my_absences_alias(message: types.Message):
    """
    Псевдокнопка: выводим список заявок с кнопками «Изменить».
    """
    await show_my_absences(message)


###############################################################################
# Запрос на удаление одобренного отсутствия
###############################################################################
@router.callback_query(lambda c: c.data.startswith("request_del:"))
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
        except Exception:
            pass

    await cb.message.answer("Запрос на удаление отправлен администратору.")
    await cb.answer()


@router.callback_query(lambda c: c.data.startswith("request_edit:"))
async def request_edit_absence(cb: CallbackQuery, state: FSMContext):
    abs_id_str = cb.data.split(":")[1]
    abs_id = int(abs_id_str)

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

    await state.update_data(abs_id=abs_id)

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


@router.callback_query(lambda c: c.data.startswith("edit_cat_"), EditAbsenceFSM.waiting_for_new_category)
async def edit_category_choice(cb: CallbackQuery, state: FSMContext):
    new_cat = cb.data.split("edit_cat_")[1]
    await state.update_data(new_cat=new_cat)
    await cb.message.answer(TEXT_ENTER_NEW_START_DATE)
    await state.set_state(EditAbsenceFSM.waiting_for_new_start_date)
    await cb.answer()


@router.message(EditAbsenceFSM.waiting_for_new_start_date)
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


@router.message(EditAbsenceFSM.waiting_for_new_end_date)
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


@router.message(EditAbsenceFSM.waiting_for_new_comment)
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

    old_row = get_absence_by_id(abs_id)
    if not old_row:
        await message.answer(TEXT_ORIGINAL_REQUEST_NOT_FOUND)
        return

    _old_user_id, old_cat, old_sd, old_ed, old_cmnt, _old_status = old_row
    old_sd_disp = format_date_display(old_sd)
    old_ed_disp = format_date_display(old_ed)
    new_sd_disp = format_date_display(new_sd)
    new_ed_disp = format_date_display(new_ed)

    req_id = create_edit_request(abs_id, new_cat, new_sd, new_ed, comment, user_id)

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

    await message.answer(
        f"Запрос на изменение заявки #{abs_id} отправлен на одобрение администратору.\n"
        f"(Старое и новое видно админу)."
    )

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
        except Exception:
            pass

    await state.clear()


@router.callback_query(lambda c: c.data.startswith("approve_edit:") or c.data.startswith("decline_edit:"))
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
        update_absence(abs_id, new_cat, new_sd, new_ed, new_comment)
        delete_edit_request(req_id)

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

        try:
            await bot.send_message(
                user_id,
                f"Ваше изменение заявки #{abs_id} одобрено!\n"
                f"Теперь: {new_cat}, {new_sd_disp}–{new_ed_disp}, {new_comment or '—'}"
            )
        except Exception:
            pass

        await cb.answer()

    else:  # "decline_edit"
        delete_edit_request(req_id)

        await cb.message.answer(f"Изменение заявки #{abs_id} отклонено.")
        try:
            await bot.send_message(
                user_id,
                f"Ваше изменение заявки #{abs_id} отклонено администратором."
            )
        except Exception:
            pass

        await cb.answer()


@router.callback_query(lambda c: c.data.startswith("approve_del:") or c.data.startswith("decline_del:"))
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
        except Exception:
            pass
    else:
        await cb.message.answer(f"Удаление #{abs_id} отклонено.")
        log_action(cb.from_user.id, f"decline_del absence {abs_id}")
        try:
            await bot.send_message(user_id, f"Админ отклонил удаление вашей заявки #{abs_id}.")
        except Exception:
            pass

    await cb.answer()


###############################################################################
# Заявки на отсутствие (pending)
###############################################################################
@router.message(lambda msg: msg.text in {"Заявки на отсутствие", "Заявки на отсутствие (pending)"})
async def show_absence_requests(message: types.Message):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

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


@router.callback_query(lambda c: c.data.startswith("approve_abs:") or c.data.startswith("decline_abs:"))
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
    except Exception:
        pass

    await cb.answer()


###############################################################################
# Показать отсутствия пользователя (админ)
###############################################################################
@router.message(lambda msg: msg.text in {"Посмотреть отсутствия сотрудника", "Показать отсутствия пользователя"})
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

    users = get_approved_users()
    if not users:
        await message.answer(TEXT_NO_APPROVED_EMPLOYEES)
        return

    kb_rows = []
    for (tid, fname, _username) in users:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"show_abs:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(TEXT_SELECT_USER, reply_markup=inline_kb)


@router.callback_query(lambda c: c.data.startswith("show_abs:"))
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
@router.message(lambda msg: msg.text in {"Удалить отсутствие сотрудника", "Удалить отсутствие пользователя"})
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


@router.callback_query(lambda c: c.data.startswith("adm_del_pickuser:"))
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


@router.callback_query(lambda c: c.data.startswith("adm_del_abs:"))
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
    except Exception:
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


@router.message(lambda msg: msg.text in {"Изменить отсутствие сотрудника", "Изменить отсутствие пользователя"})
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


@router.callback_query(lambda c: c.data.startswith("adm_edit_user:"), AdminEditAbsenceFSM.waiting_for_user)
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


@router.callback_query(lambda c: c.data.startswith("adm_edit_abs:"), AdminEditAbsenceFSM.waiting_for_absence)
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


@router.callback_query(lambda c: c.data.startswith("adm_edit_cat_"), AdminEditAbsenceFSM.waiting_for_category)
async def admin_edit_absence_category(cb: CallbackQuery, state: FSMContext):
    new_cat = cb.data.split("adm_edit_cat_")[1]
    await state.update_data(new_cat=new_cat)
    await cb.message.answer(TEXT_ENTER_NEW_START_DATE)
    await state.set_state(AdminEditAbsenceFSM.waiting_for_start_date)
    await cb.answer()


@router.message(AdminEditAbsenceFSM.waiting_for_start_date)
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


@router.message(AdminEditAbsenceFSM.waiting_for_end_date)
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


@router.message(AdminEditAbsenceFSM.waiting_for_comment)
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
    except Exception:
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


@router.message(lambda msg: msg.text in {"Выгрузить отсутствия (CSV)", "Выгрузить отсутствия в CSV"})
async def start_csv_export(message: types.Message, state: FSMContext):
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
        f"Сейчас вы собираетесь выгрузить отсутствия (CSV).\n{TEXT_ENTER_PERIOD_START_OR_CANCEL}",
        reply_markup=cancel_kb
    )

    await state.set_state(CsvExportFSM.waiting_for_start_date)


@router.message(CsvExportFSM.waiting_for_start_date)
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


@router.message(CsvExportFSM.waiting_for_end_date)
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
        return

    data = await state.get_data()
    start_date_str = data["start_date"]
    group_id = data.get("group_id")
    start_date_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()

    if end_date_obj < start_date_obj:
        await message.answer("Дата окончания не может быть раньше даты начала. Попробуйте снова.")
        return

    await state.update_data(end_date=str(end_date_obj))
    sds = str(start_date_obj)
    eds = str(end_date_obj)
    sds_disp = format_date_display(sds)
    eds_disp = format_date_display(eds)

    rows = list_approved_absences_between(sds, eds, group_id)

    logging.debug(f"Found {len(rows)} rows for CSV export from {sds} to {eds}")

    if not rows:
        await message.answer(f"Нет 'approved' отсутствий в период {sds_disp}–{eds_disp}.")
        await state.clear()
        return

    lines = ["fullname;username;category;start_date;end_date;comment"]
    for (_uid, cat, sd, ed, cmnt, fname, uname) in rows:
        cmnt_esc = (cmnt or "").replace(";", ",")
        if uname:
            user_str = f"{fname} (@{uname})"
        else:
            user_str = f"{fname}"
        sd_disp = format_date_display(sd)
        ed_disp = format_date_display(ed)
        lines.append(f"{user_str};{uname or ''};{cat};{sd_disp};{ed_disp};{cmnt_esc}")

    csv_text = "\n".join(lines)
    bom = b'\xef\xbb\xbf'
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
@router.message(lambda msg: msg.text in {"Выгрузить отсутствия за сегодня", "Отсутствия на сегодня"})
async def show_absences_today(message: types.Message):
    tg_id = message.from_user.id
    allowed, group_id, need_select = get_admin_scope(tg_id)
    if not allowed:
        if need_select:
            await message.answer(TEXT_SELECT_GROUP_FIRST)
        else:
            await message.answer(TEXT_NO_RIGHTS_ADMIN)
        return

    today_display = datetime.date.today().strftime("%d.%m.%Y")
    today_iso = datetime.date.today().isoformat()

    rows = list_approved_absences_for_date(today_iso, group_id)

    if not rows:
        await message.answer(f"На сегодня ({today_display}) нет одобренных отсутствий.")
        return

    lines = []
    for (_uid, category, sd, ed, cmnt, fullname, _username) in rows:
        start_disp = format_date_display(sd)
        end_disp = format_date_display(ed)
        user_str = fullname
        comment_str = cmnt if cmnt else "—"
        line = f"{user_str} ({category}, {start_disp} - {end_disp}), комментарий: {comment_str}"
        lines.append(line)

    result_text = f"Отсутствия на сегодня ({today_display}):\n\n" + "\n\n".join(lines)
    await message.answer(result_text)

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


@router.message(lambda msg: msg.text in {"Добавить отсутствие другому сотруднику", "Добавить отсутствие другому пользователю"})
async def add_absence_for_another_start(message: types.Message, state: FSMContext):
    if not is_user_approved(message.from_user.id):
        await message.answer("Вы не одобрены, не можете добавлять отсутствие другим.")
        return
    if not is_superadmin(message.from_user.id) and not user_has_any_group(message.from_user.id):
        await message.answer(TEXT_NOT_IN_ANY_GROUP)
        return

    await state.clear()

    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXT_CANCEL_BUTTON)]],
        resize_keyboard=True
    )
    await message.answer(
        f"Сейчас вы добавляете отсутствие другому пользователю.\n{TEXT_CANCEL_HINT}",
        reply_markup=cancel_kb
    )

    rows = get_approved_users()
    if not rows:
        await message.answer("Нет ни одного одобренного сотрудника в системе.")
        return

    kb_rows = []
    for (tid, fname, _username) in rows:
        kb_rows.append([
            InlineKeyboardButton(text=fname, callback_data=f"add_for_user:{tid}")
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(
        "Выберите сотрудника, которому хотите добавить отсутствие:",
        reply_markup=inline_kb
    )

    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_user)


@router.callback_query(lambda c: c.data.startswith("add_for_user:"), AddAbsenceForAnotherFSM.waiting_for_user)
async def pick_user_for_abs(cb: CallbackQuery, state: FSMContext):
    if not is_user_approved(cb.from_user.id):
        await cb.answer(TEXT_NOT_APPROVED_SHORT)
        return

    user_id_str = cb.data.split(":")[1]
    target_user_id = int(user_id_str)

    await state.update_data(target_user_id=target_user_id)

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


@router.callback_query(lambda c: c.data.startswith("another_cat_"), AddAbsenceForAnotherFSM.waiting_for_category)
async def pick_category_for_another(cb: CallbackQuery, state: FSMContext):
    if not is_user_approved(cb.from_user.id):
        await cb.answer(TEXT_NOT_APPROVED_SHORT)
        return

    category = cb.data.split("another_cat_")[1]
    await state.update_data(category=category)

    await cb.message.answer(
        f"Категория выбрана: {category}.\nВведите дату начала (дд.мм.гггг):"
    )
    await cb.answer()
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_start_date)


@router.message(AddAbsenceForAnotherFSM.waiting_for_start_date)
async def another_absence_start_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(TEXT_INVALID_DATE_TRY_AGAIN)
        return

    await state.update_data(start_date=str(date_obj))
    await message.answer(TEXT_ENTER_END_DATE)
    await state.set_state(AddAbsenceForAnotherFSM.waiting_for_end_date)


@router.message(AddAbsenceForAnotherFSM.waiting_for_end_date)
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


@router.message(AddAbsenceForAnotherFSM.waiting_for_comment)
async def another_absence_comment(message: types.Message, state: FSMContext):
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

    abs_id = create_absence(target_user_id, category, sd, ed, comment, "pending")

    await message.answer(
        f"Отсутствие #{abs_id} добавлено пользователю {get_user_fullname(target_user_id)}.\n"
        f"Категория: {category}, {sd_disp}–{ed_disp}\nКомментарий: {comment or '—'}\nСтатус: pending."
    )
    log_action(message.from_user.id, f"AddAbsForAnother user={target_user_id}, abs_id={abs_id}")

    try:
        await bot.send_message(
            target_user_id,
            f"Вам добавлено отсутствие #{abs_id} ({category}, {sd_disp}–{ed_disp}) от другого пользователя.\n"
            f"Комментарий: {comment or '—'}\n(статус: pending)"
        )
    except Exception:
        pass

    user_id = message.from_user.id

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
        except Exception:
            pass

    log_action(user_id, f"AddAbsForAnother user={target_user_id}, abs_id={abs_id}")

    await state.clear()
    await message.answer(TEXT_BACK_TO_MENU, reply_markup=get_role_menu(message.from_user.id))
