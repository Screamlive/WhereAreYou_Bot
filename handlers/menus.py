from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core import (
    is_superadmin,
    user_has_any_group,
    user_is_group_admin_any,
    user_is_group_reader_any,
    get_admin_groups,
    get_view_groups,
    get_role_menu,
    get_group_scope,
)
from db_repo import (
    user_exists_in_db,
    is_user_approved,
    get_last_group_id,
    set_last_group_id,
    get_group_name,
    get_group_membership_role,
)
from keyboards import (
    BACK_BUTTON_TEXT,
    not_approved_menu,
    group_admin_main_menu,
    group_admin_select_menu,
    my_absences_menu,
    superadmin_users_menu,
    superadmin_groups_menu,
    superadmin_absences_menu,
    superadmin_superadmins_menu,
    superadmin_work_group_menu,
    group_admin_requests_menu,
    group_viewer_requests_menu,
    group_admin_users_menu,
    group_viewer_users_menu,
    group_admin_absences_menu,
    group_viewer_absences_menu,
    group_admin_groups_menu,
    group_admin_groups_menu_single,
    user_groups_menu,
    no_group_groups_menu,
    user_other_absences_menu,
    no_group_menu,
)
from texts import (
    TEXT_NO_RIGHTS,
    TEXT_NOT_APPROVED_SHORT,
    TEXT_NOT_REGISTERED_LONG,
    TEXT_SECTION_GROUPS,
    TEXT_CANCELLED,
    TEXT_BACK_TO_MENU,
    TEXT_NOT_REGISTERED,
    TEXT_NOT_APPROVED,
    TEXT_UNKNOWN_COMMAND,
    TEXT_CANCEL_BUTTON,
)

router = Router()


def _superadmin_filter_label(user_id: int) -> str:
    group_id = get_last_group_id(user_id)
    if not group_id:
        return "Текущий фильтр: глобально"
    group_name = get_group_name(group_id) or f"ID={group_id}"
    return f"Текущий фильтр: {group_name}"


def _is_filter_menu_button(text: str | None) -> bool:
    if not text:
        return False
    return text in {"Рабочая группа", "Фильтр по группе"} or text.startswith("Фильтр:")


###############################################################################
# НАВИГАЦИЯ ПО МЕНЮ
###############################################################################
@router.message(lambda msg: msg.text == "Мои отсутствия")
async def open_my_absences_menu(message: types.Message):
    await message.answer("Раздел «Мои отсутствия». Выберите действие:", reply_markup=my_absences_menu)


@router.message(lambda msg: msg.text in {"Управление пользователями", "Пользователи (упр.)"})
async def open_superadmin_users_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer(
        f"Раздел «Управление пользователями».\n{_superadmin_filter_label(message.from_user.id)}",
        reply_markup=superadmin_users_menu
    )


@router.message(lambda msg: msg.text in {"Управление группами", "Группы (упр.)"})
async def open_superadmin_groups_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer(
        f"Раздел «Управление группами».\n{_superadmin_filter_label(message.from_user.id)}",
        reply_markup=superadmin_groups_menu
    )


@router.message(lambda msg: msg.text in {"Управление отсутствиями", "Отсутствия (упр.)"})
async def open_superadmin_absences_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer(
        f"Раздел «Управление отсутствиями».\n{_superadmin_filter_label(message.from_user.id)}",
        reply_markup=superadmin_absences_menu
    )


@router.message(lambda msg: msg.text in {"Управление суперадминами", "Суперадмины"})
async def open_superadmin_admins_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer(
        f"Раздел «Управление суперадминами».\n{_superadmin_filter_label(message.from_user.id)}",
        reply_markup=superadmin_superadmins_menu
    )


@router.message(lambda msg: _is_filter_menu_button(msg.text))
async def open_superadmin_work_group_menu(message: types.Message):
    if not is_superadmin(message.from_user.id):
        await message.answer(TEXT_NO_RIGHTS)
        return
    await message.answer(
        "Раздел «Фильтр по группе». Он влияет на списки/заявки в интерфейсе суперадмина, права не меняет.",
        reply_markup=superadmin_work_group_menu
    )
    await message.answer(_superadmin_filter_label(message.from_user.id))


@router.message(lambda msg: msg.text in {"Заявки в группу", "Заявки (просмотр)"})
async def open_group_requests_menu(message: types.Message):
    can_read, can_write, _group_id, need_select = get_group_scope(message.from_user.id)
    if not can_read:
        if need_select:
            await message.answer("Сначала выберите рабочую группу (кнопка «Сменить группу»).")
            return
        await message.answer(TEXT_NO_RIGHTS)
        return
    submenu = group_admin_requests_menu if can_write else group_viewer_requests_menu
    await message.answer("Раздел «Заявки в группу».", reply_markup=submenu)


@router.message(lambda msg: msg.text == "Пользователи группы")
async def open_group_users_menu(message: types.Message):
    can_read, can_write, _group_id, need_select = get_group_scope(message.from_user.id)
    if not can_read:
        if need_select:
            await message.answer("Сначала выберите рабочую группу (кнопка «Сменить группу»).")
            return
        await message.answer(TEXT_NO_RIGHTS)
        return
    submenu = group_admin_users_menu if can_write else group_viewer_users_menu
    await message.answer("Раздел «Пользователи группы».", reply_markup=submenu)


@router.message(lambda msg: msg.text in {"Управление отсутствиями группы", "Отсутствия группы"})
async def open_group_absences_menu(message: types.Message):
    can_read, can_write, _group_id, need_select = get_group_scope(message.from_user.id)
    if not can_read:
        if need_select:
            await message.answer("Сначала выберите рабочую группу (кнопка «Сменить группу»).")
            return
        await message.answer(TEXT_NO_RIGHTS)
        return
    submenu = group_admin_absences_menu if can_write else group_viewer_absences_menu
    await message.answer("Раздел «Управление отсутствиями группы».", reply_markup=submenu)


@router.message(lambda msg: msg.text == "Группы")
async def open_groups_menu(message: types.Message):
    tg_id = message.from_user.id
    if is_superadmin(tg_id):
        await message.answer("Используйте раздел «Управление группами».")
        return
    if not user_has_any_group(tg_id):
        await message.answer(TEXT_SECTION_GROUPS, reply_markup=no_group_groups_menu)
        return
    if user_is_group_reader_any(tg_id):
        view_groups = get_view_groups(tg_id)
        if len(view_groups) == 1:
            await message.answer(TEXT_SECTION_GROUPS, reply_markup=group_admin_groups_menu_single)
        else:
            await message.answer(TEXT_SECTION_GROUPS, reply_markup=group_admin_groups_menu)
        return
    await message.answer(TEXT_SECTION_GROUPS, reply_markup=user_groups_menu)


@router.message(
    lambda msg: msg.text in {"Отсутствия для другого пользователя", "Для другого пользователя", "Для другого"}
)
async def open_other_absences_menu(message: types.Message):
    if not is_user_approved(message.from_user.id):
        await message.answer(TEXT_NOT_APPROVED_SHORT)
        return
    await message.answer("Раздел «Отсутствия для другого пользователя».", reply_markup=user_other_absences_menu)


@router.message(lambda msg: msg.text == "Текущая группа")
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
        if not user_is_group_reader_any(user_id):
            await message.answer("У вас нет прав на работу с группой.")
            return

    can_read, _can_write, group_id, need_select = get_group_scope(user_id)
    if not can_read:
        if need_select:
            await message.answer("Группа не выбрана. Нажмите «Сменить группу».")
            return
        await message.answer("У вас нет доступа к рабочей группе.")
        return

    name = get_group_name(group_id) or f"ID={group_id}"
    await message.answer(f"Текущая группа: {name}")


###############################################################################
# /start
###############################################################################
@router.message(Command("start"))
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
        await message.answer(
            f"Здравствуйте, Суперадминистратор!\n{_superadmin_filter_label(tg_id)}",
            reply_markup=get_role_menu(tg_id)
        )
        return

    managed_groups = get_view_groups(tg_id)
    if managed_groups:
        if len(managed_groups) == 1:
            only_gid, only_name, only_role = managed_groups[0]
            set_last_group_id(tg_id, only_gid)
            role_title = "Администратор группы" if only_role == "admin" else "Наблюдатель группы"
            await message.answer(
                f"Здравствуйте, {role_title}! Рабочая группа: {only_name}",
                reply_markup=get_role_menu(tg_id)
            )
            return

        selected_gid = get_last_group_id(tg_id)
        if selected_gid and selected_gid in {gid for gid, _name, _role in managed_groups}:
            gname = get_group_name(selected_gid) or "выбрана"
            role = get_group_membership_role(tg_id, selected_gid)
            role_title = "Администратор группы" if role == "admin" else "Наблюдатель группы"
            await message.answer(
                f"Здравствуйте, {role_title}! Рабочая группа: {gname}",
                reply_markup=get_role_menu(tg_id)
            )
            return

        # несколько групп и нет выбранной — просим выбрать
        kb_rows = []
        for gid, name, role in managed_groups:
            kb_rows.append([InlineKeyboardButton(text=name, callback_data=f"set_group:{gid}")])
        inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await message.answer(
            "Здравствуйте! Выберите рабочую группу:",
            reply_markup=inline_kb
        )
        await message.answer(
            "После выбора появится меню работы с группой.",
            reply_markup=group_admin_select_menu
        )
        return

    await message.answer("Добро пожаловать, Пользователь!", reply_markup=get_role_menu(tg_id))


###############################################################################
# Вернуться в меню (reply-кнопка)
###############################################################################
@router.message(lambda msg: msg.text == BACK_BUTTON_TEXT)
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    if is_superadmin(message.from_user.id):
        await message.answer(
            f"{TEXT_BACK_TO_MENU}\n{_superadmin_filter_label(message.from_user.id)}",
            reply_markup=get_role_menu(message.from_user.id)
        )
        return
    await message.answer(TEXT_BACK_TO_MENU, reply_markup=get_role_menu(message.from_user.id))


#######################
# Глобальный хендлер TEXT_CANCEL_BUTTON (Reply-кнопка)
###############################
@router.message(StateFilter("*"), lambda msg: msg.text == TEXT_CANCEL_BUTTON)
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
@router.message()
async def fallback_handler(message: types.Message):
    tg_id = message.from_user.id
    if not user_exists_in_db(tg_id):
        await message.answer(TEXT_NOT_REGISTERED, reply_markup=not_approved_menu)
        return
    if not is_user_approved(tg_id):
        await message.answer(TEXT_NOT_APPROVED, reply_markup=not_approved_menu)
        return

    await message.answer(TEXT_UNKNOWN_COMMAND, reply_markup=get_role_menu(tg_id))
