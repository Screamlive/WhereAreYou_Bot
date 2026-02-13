from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BACK_BUTTON_TEXT = "Вернуться в меню"
TWO_COLUMN_MAX_LABEL_LEN = 22


def _build_menu(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    normalized_rows: list[list[KeyboardButton]] = []
    for row in rows:
        # Telegram client controls text centering; for long two-column rows
        # we force single-column layout to avoid ugly wrapping on mobile.
        if len(row) > 1 and any(len(text) > TWO_COLUMN_MAX_LABEL_LEN for text in row):
            for text in row:
                normalized_rows.append([KeyboardButton(text=text)])
            continue
        normalized_rows.append([KeyboardButton(text=text) for text in row])
    return ReplyKeyboardMarkup(keyboard=normalized_rows, resize_keyboard=True)

not_approved_menu = _build_menu([
    ["Зарегистрироваться"],
])

# Главные меню
superadmin_main_menu = _build_menu([
    ["Отсутствия на сегодня", "Мои отсутствия"],
    ["Отсутствия (упр.)", "Группы (упр.)"],
    ["Пользователи (упр.)", "Суперадмины"],
    ["Рабочая группа"],
])

group_admin_main_menu = _build_menu([
    ["Отсутствия на сегодня", "Мои отсутствия"],
    ["Отсутствия группы", "Заявки в группу"],
    ["Пользователи группы", "Группы"],
])

user_main_menu = _build_menu([
    ["Мои отсутствия", "Группы"],
    ["Для другого пользователя"],
])

no_group_menu = _build_menu([
    ["Группы"],
])

group_admin_select_menu = _build_menu([
    ["Выбрать группу"],
])

# Подменю
my_absences_menu = _build_menu([
    ["Добавить отсутствие"],
    ["Мои заявки"],
    [BACK_BUTTON_TEXT],
])

superadmin_users_menu = _build_menu([
    ["Заявки регистрации", "Список пользователей"],
    ["Изменить ФИО", "Показать @username"],
    ["Удалить из бота"],
    [BACK_BUTTON_TEXT],
])

superadmin_groups_menu = _build_menu([
    ["Заявки в группу"],
    ["Список групп", "Состав группы"],
    ["Создать группу", "Удалить группу"],
    ["Добавить в группу", "Удалить из группы"],
    ["Назначить администратора группы", "Отозвать администратора группы"],
    [BACK_BUTTON_TEXT],
])

superadmin_absences_menu = _build_menu([
    ["Отсутствия на сегодня", "Заявки на отсутствие"],
    ["Отсутствия сотрудника", "Выгрузить в CSV"],
    ["Добавить другому"],
    ["Изменить у сотрудника", "Удалить у сотрудника"],
    [BACK_BUTTON_TEXT],
])

superadmin_superadmins_menu = _build_menu([
    ["Список суперадминов"],
    ["Сделать суперадмином", "Снять суперадмина"],
    [BACK_BUTTON_TEXT],
])

superadmin_work_group_menu = _build_menu([
    ["Текущая группа"],
    ["Сменить группу", "Глобально"],
    [BACK_BUTTON_TEXT],
])

group_admin_requests_menu = _build_menu([
    ["Заявки на вступление", "Заявки на выход"],
    [BACK_BUTTON_TEXT],
])

group_admin_users_menu = _build_menu([
    ["Список пользователей", "Список админов группы"],
    ["Удалить из группы"],
    [BACK_BUTTON_TEXT],
])

group_admin_absences_menu = _build_menu([
    ["Отсутствия на сегодня", "Заявки на отсутствие"],
    ["Отсутствия сотрудника", "Выгрузить в CSV"],
    ["Добавить другому"],
    ["Изменить у сотрудника", "Удалить у сотрудника"],
    [BACK_BUTTON_TEXT],
])

group_admin_groups_menu = _build_menu([
    ["Текущая группа", "Сменить группу"],
    ["Мои группы"],
    ["Запроситься в группу", "Выйти из группы"],
    [BACK_BUTTON_TEXT],
])

group_admin_groups_menu_single = _build_menu([
    ["Текущая группа"],
    ["Мои группы"],
    ["Запроситься в группу", "Выйти из группы"],
    [BACK_BUTTON_TEXT],
])

user_groups_menu = _build_menu([
    ["Мои группы"],
    ["Запроситься в группу", "Выйти из группы"],
    [BACK_BUTTON_TEXT],
])

no_group_groups_menu = _build_menu([
    ["Запроситься в группу"],
    [BACK_BUTTON_TEXT],
])

user_other_absences_menu = _build_menu([
    ["Добавить другому"],
    [BACK_BUTTON_TEXT],
])
