import os

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

BACK_BUTTON_TEXT = "Вернуться в меню"
TWO_COLUMN_MAX_LABEL_LEN = 22
FILTER_SCOPE_LABEL_MAX_LEN = 24


def _get_webapp_url() -> str:
    from config import WEBAPP_URL  # local import to avoid hard failure if absent at module import

    env_value = (os.getenv("WEBAPP_URL") or "").strip()
    if env_value:
        return env_value
    return (WEBAPP_URL or "").strip()


def _build_webapp_button() -> KeyboardButton | None:
    try:
        url = _get_webapp_url()
    except Exception:
        url = (os.getenv("WEBAPP_URL") or "").strip()
    if not url:
        return None
    return KeyboardButton(text="Пересечения (WebApp)", web_app=WebAppInfo(url=url))


def _build_menu(rows: list[list[str | KeyboardButton]]) -> ReplyKeyboardMarkup:
    normalized_rows: list[list[KeyboardButton]] = []
    for row in rows:
        normalized_row: list[KeyboardButton] = []
        for item in row:
            if isinstance(item, KeyboardButton):
                normalized_row.append(item)
            else:
                normalized_row.append(KeyboardButton(text=item))

        # Telegram client controls text centering; for long two-column rows
        # we force single-column layout to avoid ugly wrapping on mobile.
        if len(normalized_row) > 1 and any(len(btn.text or "") > TWO_COLUMN_MAX_LABEL_LEN for btn in normalized_row):
            for button in normalized_row:
                normalized_rows.append([button])
            continue
        normalized_rows.append(normalized_row)
    return ReplyKeyboardMarkup(keyboard=normalized_rows, resize_keyboard=True)

def _shorten_label(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_superadmin_filter_button(scope_name: str | None) -> str:
    normalized = (scope_name or "глобально").strip() or "глобально"
    short = _shorten_label(normalized, FILTER_SCOPE_LABEL_MAX_LEN)
    return f"Фильтр: {short}"


def build_superadmin_main_menu(scope_name: str | None) -> ReplyKeyboardMarkup:
    rows: list[list[str | KeyboardButton]] = [
        ["Отсутствия на сегодня", "Мои отсутствия"],
        ["Отсутствия (упр.)", "Группы (упр.)"],
        ["Пользователи (упр.)", "Суперадмины"],
        [build_superadmin_filter_button(scope_name)],
    ]
    webapp_button = _build_webapp_button()
    if webapp_button:
        rows.append([webapp_button])
    return _build_menu(rows)


not_approved_menu = _build_menu([
    ["Зарегистрироваться"],
])

# Главные меню
superadmin_main_menu = build_superadmin_main_menu("глобально")

_group_admin_main_rows: list[list[str | KeyboardButton]] = [
    ["Отсутствия на сегодня", "Мои отсутствия"],
    ["Отсутствия группы", "Заявки в группу"],
    ["Пользователи группы", "Группы"],
]
_webapp_button = _build_webapp_button()
if _webapp_button:
    _group_admin_main_rows.append([_webapp_button])
group_admin_main_menu = _build_menu(_group_admin_main_rows)

_group_viewer_main_rows: list[list[str | KeyboardButton]] = [
    ["Отсутствия на сегодня", "Мои отсутствия"],
    ["Отсутствия группы", "Заявки (просмотр)"],
    ["Пользователи группы", "Группы"],
]
_webapp_button = _build_webapp_button()
if _webapp_button:
    _group_viewer_main_rows.append([_webapp_button])
group_viewer_main_menu = _build_menu(_group_viewer_main_rows)

_user_main_rows: list[list[str | KeyboardButton]] = [
    ["Мои отсутствия", "Группы"],
    ["Для другого"],
]
_webapp_button = _build_webapp_button()
if _webapp_button:
    _user_main_rows.append([_webapp_button])
user_main_menu = _build_menu(_user_main_rows)

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
    ["Назначить админа", "Снять админа группы"],
    ["Назначить наблюдателя", "Снять наблюдателя"],
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
    ["Выбрать группу", "Глобально"],
    [BACK_BUTTON_TEXT],
])

group_admin_requests_menu = _build_menu([
    ["Заявки на вступление", "Заявки на выход"],
    ["Заявки на роль"],
    [BACK_BUTTON_TEXT],
])

group_viewer_requests_menu = _build_menu([
    ["Заявки на вступление", "Заявки на выход"],
    ["Заявки на роль"],
    [BACK_BUTTON_TEXT],
])

group_admin_users_menu = _build_menu([
    ["Список пользователей", "Список админов группы"],
    ["Назначить наблюдателя", "Снять наблюдателя"],
    ["Удалить из группы"],
    [BACK_BUTTON_TEXT],
])

group_viewer_users_menu = _build_menu([
    ["Список пользователей", "Список админов группы"],
    [BACK_BUTTON_TEXT],
])

group_admin_absences_menu = _build_menu([
    ["Отсутствия на сегодня", "Заявки на отсутствие"],
    ["Отсутствия сотрудника", "Выгрузить в CSV"],
    ["Добавить другому"],
    ["Изменить у сотрудника", "Удалить у сотрудника"],
    [BACK_BUTTON_TEXT],
])

group_viewer_absences_menu = _build_menu([
    ["Отсутствия на сегодня", "Заявки на отсутствие"],
    ["Отсутствия сотрудника", "Выгрузить в CSV"],
    [BACK_BUTTON_TEXT],
])

group_admin_groups_menu = _build_menu([
    ["Текущая группа", "Сменить группу"],
    ["Мои группы"],
    ["Стать наблюдателем"],
    ["Запроситься в группу", "Выйти из группы"],
    [BACK_BUTTON_TEXT],
])

group_admin_groups_menu_single = _build_menu([
    ["Текущая группа"],
    ["Мои группы"],
    ["Стать наблюдателем"],
    ["Запроситься в группу", "Выйти из группы"],
    [BACK_BUTTON_TEXT],
])

user_groups_menu = _build_menu([
    ["Мои группы"],
    ["Стать наблюдателем"],
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
