from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BACK_BUTTON_TEXT = "Вернуться в меню"

not_approved_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Зарегистрироваться")],
    ],
    resize_keyboard=True
)

# Главные меню
superadmin_main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мои отсутствия"), KeyboardButton(text="Управление пользователями")],
        [KeyboardButton(text="Управление группами"), KeyboardButton(text="Управление отсутствиями")],
        [KeyboardButton(text="Отсутствия на сегодня"), KeyboardButton(text="Управление суперадминами")],
        [KeyboardButton(text="Рабочая группа")]
    ],
    resize_keyboard=True
)

group_admin_main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мои отсутствия"), KeyboardButton(text="Заявки в группу")],
        [KeyboardButton(text="Пользователи группы"), KeyboardButton(text="Управление отсутствиями группы")],
        [KeyboardButton(text="Группы")]
    ],
    resize_keyboard=True
)

user_main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мои отсутствия"), KeyboardButton(text="Группы")],
        [KeyboardButton(text="Отсутствия для другого пользователя")]
    ],
    resize_keyboard=True
)

no_group_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Группы")]
    ],
    resize_keyboard=True
)

group_admin_select_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Выбрать группу")]
    ],
    resize_keyboard=True
)

# Подменю
my_absences_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить отсутствие")],
        [KeyboardButton(text="Мои заявки")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

superadmin_users_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Список пользователей"), KeyboardButton(text="Список запросов (регистрация)")],
        [KeyboardButton(text="Изменить имя пользователя"), KeyboardButton(text="Показать @username")],
        [KeyboardButton(text="Удалить пользователя из бота")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

superadmin_groups_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Создать группу"), KeyboardButton(text="Удалить группу")],
        [KeyboardButton(text="Список групп")],
        [KeyboardButton(text="Назначить администратора группы"), KeyboardButton(text="Отозвать администратора группы")],
        [KeyboardButton(text="Добавить пользователя в группу"), KeyboardButton(text="Удалить пользователя из группы")],
        [KeyboardButton(text="Список пользователей группы")],
        [KeyboardButton(text="Заявки в группу")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

superadmin_absences_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Заявки на отсутствие (pending)")],
        [KeyboardButton(text="Показать отсутствия пользователя")],
        [KeyboardButton(text="Изменить отсутствие пользователя"), KeyboardButton(text="Удалить отсутствие пользователя")],
        [KeyboardButton(text="Добавить отсутствие другому пользователю")],
        [KeyboardButton(text="Выгрузить отсутствия в CSV")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

superadmin_superadmins_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить права суперадминистратора"), KeyboardButton(text="Отозвать права суперадминистратора")],
        [KeyboardButton(text="Список суперадминистраторов")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

superadmin_work_group_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Текущая группа")],
        [KeyboardButton(text="Сменить группу"), KeyboardButton(text="Глобально")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

group_admin_requests_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Заявки на вступление"), KeyboardButton(text="Заявки на выход")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

group_admin_users_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Список пользователей"), KeyboardButton(text="Список администраторов группы")],
        [KeyboardButton(text="Удалить пользователя из группы")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

group_admin_absences_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Заявки на отсутствие (pending)")],
        [KeyboardButton(text="Показать отсутствия пользователя")],
        [KeyboardButton(text="Изменить отсутствие пользователя"), KeyboardButton(text="Удалить отсутствие пользователя")],
        [KeyboardButton(text="Добавить отсутствие другому пользователю")],
        [KeyboardButton(text="Выгрузить отсутствия в CSV")],
        [KeyboardButton(text="Отсутствия на сегодня")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

group_admin_groups_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мои группы")],
        [KeyboardButton(text="Запроситься в группу"), KeyboardButton(text="Выйти из группы")],
        [KeyboardButton(text="Текущая группа"), KeyboardButton(text="Сменить группу")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

group_admin_groups_menu_single = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мои группы")],
        [KeyboardButton(text="Запроситься в группу"), KeyboardButton(text="Выйти из группы")],
        [KeyboardButton(text="Текущая группа")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

user_groups_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мои группы")],
        [KeyboardButton(text="Запроситься в группу"), KeyboardButton(text="Выйти из группы")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

no_group_groups_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Запроситься в группу")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)

user_other_absences_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить отсутствие другому пользователю")],
        [KeyboardButton(text=BACK_BUTTON_TEXT)]
    ],
    resize_keyboard=True
)
