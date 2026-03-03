# WhereAreYou_Bot

Telegram-бот для учета отсутствий сотрудников с поддержкой групп, заявок,
наблюдателей групп, групповых администраторов и суперадминов.

## Быстрый старт

1) Установите зависимости и подготовьте окружение:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Создайте конфиг и укажите токен:
```
cp config_example.py config.py
```

3) Запуск:
```
python bot.py
```

При первом запуске создается SQLite‑база `bot_database.db`.

## Конфигурация

Файл `config.py`:
- `TOKEN` — токен бота от BotFather.
- `DB_NAME` — имя файла SQLite.
- `WEBAPP_URL` — публичный HTTPS URL WebApp (например, `https://example.com/webapp`).

Важно: `database.py` использует имя базы по умолчанию `bot_database.db`.
Если меняете `DB_NAME`, синхронизируйте значение в `database.py`.

## Первичный суперадмин

Бот не создает суперадмина автоматически. Сценарий:
1) Запустите бота и зарегистрируйтесь через кнопку «Зарегистрироваться».
2) Назначьте себя суперадмином в БД.

Пример (после регистрации, подставьте свой telegram_id):
```
sqlite3 bot_database.db "UPDATE users SET is_admin=1, is_approved=1 WHERE telegram_id=123456789;"
```

## Тесты

По умолчанию используются `unittest`:
```
./.venv/bin/python -m unittest discover -s tests
```

Если хотите запускать через `pytest`:
```
pip install -r requirements-dev.txt
pytest
```

## WebApp (read-only пересечения)

Вход для пользователя:
- кнопка **«Пересечения (WebApp)»** в главном меню бота;
- кнопка показывается, если задан `WEBAPP_URL` (в `config.py` или через env `WEBAPP_URL`).

Обязательные условия для Telegram WebApp в production:
- публичный HTTPS домен;
- домен прописан в BotFather через `/setdomain`;
- backend не выдает данные без валидного `initData`.

Запуск backend WebApp:
```
source .venv/bin/activate
python webapp_api.py
```

Открытие в браузере для локальной проверки (без Telegram):
```
WEBAPP_ALLOW_DEV_FALLBACK=1 python webapp_api.py
curl -H "X-Telegram-User-Id: <telegram_id>" "http://127.0.0.1:8080/webapp/v1/me"
```

Важно по безопасности:
- для production используется только Telegram `initData` (dev fallback выключен по умолчанию);
- URL WebApp публичный, но запросы без валидного `initData` получают `401/403`;
- для Telegram WebApp нужен HTTPS-домен и настройка домена через BotFather (`/setdomain`).

## Nginx и домен (production)

Системные пакеты (Ubuntu):
```
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

1) Настройка DNS (Cloudflare):
- `A` запись `bot-test.example.com` -> IP тестового сервера;
- `A` запись `bot.example.com` -> IP продового сервера.

2) Поднимите backend WebApp:
```
source .venv/bin/activate
WEBAPP_PORT=8080 WEBAPP_ALLOW_DEV_FALLBACK=0 python webapp_api.py
```

3) Пример Nginx-конфига:
- `deploy/nginx/telegram_webapp.conf.example`

4) Подключите конфиг и перезагрузите Nginx:
```
sudo cp deploy/nginx/telegram_webapp.conf.example /etc/nginx/sites-available/telegram_webapp
sudo ln -s /etc/nginx/sites-available/telegram_webapp /etc/nginx/sites-enabled/telegram_webapp
sudo nginx -t
sudo systemctl reload nginx
```

5) Выпустите TLS сертификат:
```
sudo certbot --nginx -d bot-test.example.com
```

6) Пропишите URL WebApp для бота:
```
# config.py
WEBAPP_URL = "https://bot-test.example.com/webapp"
WEBAPP_ALLOW_DEV_FALLBACK = False
```

7) В BotFather для соответствующего бота:
```
/setdomain
bot-test.example.com
```

8) Перезапустите бота и WebApp API.

Примечание:
- `requirements-system.txt` содержит список системных пакетов для деплоя.

Доступный функционал:
- scope: `Глобально / Группа / Суперадмины` (в зависимости от роли);
- период: `Текущий год / Текущий месяц / Следующие 90 дней`;
- фильтры: статусы, категории, поиск по ФИО/username;
- `Конфликт от`: подсветка дней с высокой нагрузкой;
- `Экспорт XLSX`: выгрузка текущего вида с учетом активных фильтров и ACL.

## Ежедневные уведомления

Для ежедневных сводок используйте user‑timer systemd (универсальный вариант).
Файлы лежат в `deploy/systemd-user/`.

Быстрый запуск (установит зависимости и настроит таймер):
```
bash deploy/setup.sh
```

Установка:
```
mkdir -p ~/.config/systemd/user
cp deploy/systemd-user/telegram_bot_notify.service ~/.config/systemd/user/
cp deploy/systemd-user/telegram_bot_notify.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now telegram_bot_notify.timer
systemctl --user status telegram_bot_notify.timer
```

Чтобы таймер работал без активной сессии пользователя:
```
sudo loginctl enable-linger $USER
```

## Сервисная рассылка

Для операционных объявлений есть CLI-скрипт `broadcast.py`.

Примеры:
```
# Предпросмотр получателей без отправки
python broadcast.py --audience approved --text "Тестовая рассылка" --dry-run

# Рассылка всем одобренным
python broadcast.py --audience approved --file CHANGELOG.md

# Рассылка только актуального блока CHANGELOG (верхний раздел)
python broadcast.py --audience approved --changelog-latest

# Рассылка участникам конкретной группы
python broadcast.py --audience group:1 --text "Сообщение для группы 1"

# Рассылка суперадминам (не более 5 получателей)
python broadcast.py --audience superadmins --text "Проверка канала" --limit 5
```

Поддерживаемые аудитории:
- `all`
- `approved`
- `group:<id>`
- `superadmins`
- `group_admins`

## Как вести CHANGELOG

Рекомендуемый формат:
- каждый релиз — отдельный блок уровня `##`, новый блок добавляется сверху;
- заголовок блока: `## YYYY-MM-DD — Краткое название релиза`;
- внутри блока — только изменения, важные для пользователей;
- прошлые блоки не удаляются, история накапливается.

Пример:
```
## 2026-02-19 — Обновление уведомлений
- Добавлен фильтр уведомлений суперадмина по выбранной группе.
- Исправлены пересечения: теперь учитывают активный фильтр суперадмина.
```

Для рассылки последнего релиза используйте:
```
python broadcast.py --audience approved --changelog-latest --dry-run
python broadcast.py --audience approved --changelog-latest
```

## Документация

- Подробное описание функций и ролей — в `DOCUMENTATION.md`.
- Короткий пользовательский changelog — в `CHANGELOG.md`.

## Структура проекта

- `bot.py` — точка входа, регистрация роутеров.
- `handlers/` — хендлеры по доменам (админ, группы, отсутствия, меню).
- `db_repo.py` — слой работы с БД.
- `database.py` — создание таблиц SQLite.
- `core.py` — общие проверки ролей и меню.
- `keyboards.py` — клавиатуры.
- `texts.py` / `utils.py` — общие тексты и утилиты.
- `tests/` — тесты.
- `config.py` — конфиг с токеном (не хранится в git).
- `config_example.py` — пример конфига.
