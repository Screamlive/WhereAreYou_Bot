# Документация проекта

## Назначение

`WhereAreYou_Bot` помогает учитывать отсутствия сотрудников, согласовывать заявки, работать с группами и наблюдателями, а также сопровождать runtime через отдельную CLI-панель.

Проект состоит из четырех практических контуров:

- Telegram-бот;
- read-only WebApp для пересечений;
- worker ежедневных уведомлений;
- ops CLI для сопровождения, backup и мониторинга.

## Актуальные точки входа

Пользовательские точки входа:

- `python bot.py`
- `python webapp_api.py`
- `python notifications.py`
- `python manage.py`
- `./manage`

Фактическая реализация лежит в `app/entrypoints/`:

- `app/entrypoints/bot_main.py`
- `app/entrypoints/webapp_main.py`
- `app/entrypoints/notifications_main.py`

Корневые модули `bot.py`, `webapp_api.py`, `webapp_readonly.py`, `webapp_export.py`, `settings.py`, `db_repo.py` сохранены как compatibility shim'ы.

## Конфигурация

### Что реально нужно для запуска

В текущей версии проекта `config.py` должен существовать. Причина простая: часть legacy-кода импортирует `config` напрямую, а не только через централизованный settings-layer.

Базовый bootstrap:

```bash
cp config_example.py config.py
```

Минимальный набор для локального запуска:

- `TOKEN`
- `DB_NAME`
- `WEBAPP_URL` при использовании кнопки `Пересечения (WebApp)`

### Источники настроек

Для параметров, которые читаются через `app.config.settings`, порядок такой:

1. env процесса;
2. путь из `TELEGRAM_BOT_ENV_FILE`;
3. `~/.config/telegram_bot/telegram_bot.env`;
4. `/etc/telegram_bot/telegram_bot.env`;
5. `./.env`;
6. `config.py`.

Но это не означает, что весь проект уже целиком env-first.

### Практический статус параметров

Надежно читаются через env/settings:

- `TOKEN`
- `WEBAPP_HOST`
- `WEBAPP_PORT`
- `WEBAPP_ALLOW_DEV_FALLBACK`
- `WEBAPP_ALLOW_INITDATA_COMPAT`
- `WEBAPP_RATE_LIMIT_MAX_REQUESTS`
- `WEBAPP_RATE_LIMIT_WINDOW_SEC`
- `MONITOR_NGINX_ENABLED`
- `MONITOR_NGINX_UNIT`

Используются напрямую из `config.py` в части legacy-кода:

- `DB_NAME`
- некоторые `WEBAPP_*` значения в Telegram menu-layer

### Ограничение по `DB_NAME`

Селектор пути БД пока не централизован полностью.

- `database.py` инициализирует схему через собственный `DB_NAME` с дефолтом `bot_database.db`.
- SQL-репозитории используют `DB_NAME` из `config.py`.
- ops backup/restore используют `DB_NAME` из env или дефолт `bot_database.db`.

Рекомендация, соответствующая текущей реализации:

- для обычного использования оставить `DB_NAME = "bot_database.db"`;
- при переносе БД проверять вручную, что runtime, `database.init_db()` и backup-команды работают с одним и тем же файлом.

## Роли и состояния

### Состояния пользователя

- не зарегистрирован -> записи в `users` нет;
- зарегистрирован, но не одобрен -> `is_approved = 0`;
- одобрен -> `is_approved = 1`.

### Роли

- суперадмин -> глобальная роль `is_admin = 1`;
- администратор группы -> membership role `admin`;
- наблюдатель группы -> membership role `viewer`;
- участник группы -> membership role `member`.

### Что определяет меню

- если пользователь не одобрен -> только регистрация;
- если пользователь одобрен, но не состоит ни в одной группе -> только раздел `Группы`;
- если пользователь суперадмин -> глобальное меню суперадмина;
- если пользователь админ/наблюдатель одной группы -> рабочая группа выбирается автоматически;
- если у админа/наблюдателя несколько групп и не задан `last_group_id` -> сначала нужно выбрать рабочую группу.

## Пользовательские сценарии

### Регистрация

1. Пользователь нажимает `/start`.
2. Если записи нет, бот предлагает `Зарегистрироваться`.
3. Пользователь вводит ФИО.
4. Заявка отправляется всем суперадминам.
5. Суперадмин одобряет или отклоняет пользователя inline-кнопкой либо командами `/approve` / `/decline`.

### Работа с группами

Поддерживаются:

- заявка на вступление (`join`);
- заявка на выход (`leave`);
- заявка на роль наблюдателя (`group_role_requests`, `target_role = viewer`);
- ручное добавление пользователя в группу суперадмином;
- массовое добавление пользователей в группу суперадмином;
- назначение и снятие администраторов группы;
- назначение и снятие наблюдателей.

### Работа с отсутствиями

Категории:

- `vacation`
- `sick`
- `dayoff`
- `other`

Статусы:

- `pending`
- `approved`
- `declined`

Поддерживаются сценарии:

- создать отсутствие для себя;
- создать отсутствие за другого сотрудника;
- просмотреть свои заявки;
- отправить запрос на изменение уже существующего отсутствия;
- отправить запрос на удаление отсутствия;
- согласовать или отклонить заявку как админ;
- выгрузить CSV по отсутствиям;
- посмотреть отсутствия на сегодня.

При создании собственного отсутствия:

- бот проверяет пересечения с другими сотрудниками;
- если пересечения есть, пользователю показывается предупреждение и отдельное подтверждение отправки.

### Ежедневные уведомления

Есть отдельный worker `notifications.py`, который формирует:

- сводку для администраторов групп по pending join и pending absences;
- сводку для суперадмина по регистрациям и групповым pending заявкам.

Уведомления отправляются только если есть что отправлять.

## Меню Telegram-бота

Ниже перечислены реальные reply-меню из `keyboards.py`.

### Неодобренный пользователь

- `Зарегистрироваться`

### Пользователь без групп

Главное меню:

- `Группы`

Раздел `Группы`:

- `Запроситься в группу`
- `Вернуться в меню`

### Обычный пользователь

Главное меню:

- `Мои отсутствия`
- `Группы`
- `Для другого`
- `Пересечения (WebApp)` если настроен `WEBAPP_URL`

Раздел `Мои отсутствия`:

- `Добавить отсутствие`
- `Мои заявки`
- `Вернуться в меню`

Раздел `Группы`:

- `Мои группы`
- `Стать наблюдателем`
- `Запроситься в группу`
- `Выйти из группы`
- `Вернуться в меню`

Раздел `Для другого`:

- `Добавить другому`
- `Вернуться в меню`

### Администратор группы

Главное меню:

- `Отсутствия на сегодня`
- `Мои отсутствия`
- `Отсутствия группы`
- `Заявки в группу`
- `Пользователи группы`
- `Группы`
- `Пересечения (WebApp)` если настроен `WEBAPP_URL`

Раздел `Заявки в группу`:

- `Заявки на вступление`
- `Заявки на выход`
- `Заявки на роль`
- `Вернуться в меню`

Раздел `Пользователи группы`:

- `Список пользователей`
- `Список админов группы`
- `Назначить наблюдателя`
- `Снять наблюдателя`
- `Удалить из группы`
- `Вернуться в меню`

Раздел `Отсутствия группы`:

- `Отсутствия на сегодня`
- `Заявки на отсутствие`
- `Отсутствия сотрудника`
- `Выгрузить в CSV`
- `Добавить другому`
- `Изменить у сотрудника`
- `Удалить у сотрудника`
- `Вернуться в меню`

Раздел `Группы`:

- `Текущая группа`
- `Сменить группу` если групп несколько
- `Мои группы`
- `Стать наблюдателем`
- `Запроситься в группу`
- `Выйти из группы`
- `Вернуться в меню`

### Наблюдатель группы

Главное меню:

- `Отсутствия на сегодня`
- `Мои отсутствия`
- `Отсутствия группы`
- `Заявки (просмотр)`
- `Пользователи группы`
- `Группы`
- `Пересечения (WebApp)` если настроен `WEBAPP_URL`

Отличия от админа группы:

- может читать, но не может согласовывать и менять состав группы;
- не может изменять отсутствия других пользователей;
- при открытии pending-заявок на отсутствие интерфейс явно сообщает о режиме наблюдателя.

### Суперадмин

Главное меню:

- `Отсутствия на сегодня`
- `Мои отсутствия`
- `Отсутствия (упр.)`
- `Группы (упр.)`
- `Пользователи (упр.)`
- `Суперадмины`
- `Фильтр: ...`
- `Пересечения (WebApp)` если настроен `WEBAPP_URL`

Раздел `Пользователи (упр.)`:

- `Заявки регистрации`
- `Список пользователей`
- `Изменить ФИО`
- `Показать @username`
- `Удалить из бота`
- `Вернуться в меню`

Раздел `Группы (упр.)`:

- `Заявки в группу`
- `Список групп`
- `Состав группы`
- `Создать группу`
- `Удалить группу`
- `Добавить в группу`
- `Удалить из группы`
- `Назначить админа`
- `Снять админа группы`
- `Назначить наблюдателя`
- `Снять наблюдателя`
- `Вернуться в меню`

Раздел `Отсутствия (упр.)`:

- `Отсутствия на сегодня`
- `Заявки на отсутствие`
- `Отсутствия сотрудника`
- `Выгрузить в CSV`
- `Добавить другому`
- `Изменить у сотрудника`
- `Удалить у сотрудника`
- `Вернуться в меню`

Раздел `Суперадмины`:

- `Список суперадминов`
- `Сделать суперадмином`
- `Снять суперадмина`
- `Вернуться в меню`

Раздел `Фильтр по группе`:

- `Текущая группа`
- `Выбрать группу`
- `Глобально`
- `Вернуться в меню`

## Команды бота

Есть явные команды, которые реально обрабатываются в хендлерах:

- `/start`
- `/webapp`
- `/approve <telegram_id>`
- `/decline <telegram_id>`
- `/refresh_menu`

`/webapp` эквивалентен нажатию кнопки `Пересечения (WebApp)`.

## WebApp

### Назначение

WebApp не заменяет чат-бот. Это read-only интерфейс для анализа пересечений и экспорта.

### Что отдает backend

`GET /webapp/v1/me`

- профиль пользователя;
- его роль для WebApp;
- допустимые scope;
- список групп;
- default scope.

`GET /webapp/v1/overlaps`

- список пользователей в текущем срезе;
- интервалы отсутствий;
- `daily_load` по дням;
- `meta.total_users`;
- `meta.total_intervals`;
- `meta.max_absent_users`.

`GET /webapp/v1/absence/{absence_id}`

- детали выбранного отсутствия.

`GET /webapp/v1/export/xlsx`

- XLSX-файл текущего вида.

### Реальные ACL правила

Обычный пользователь, наблюдатель и админ группы:

- имеют только scope `group`;
- могут видеть только свои группы.

Суперадмин:

- имеет scope `global`, `group`, `superadmins`;
- может выбрать группу по `last_group_id` или работать глобально.

Просмотр конкретного отсутствия:

- суперадмин видит любое;
- обычный пользователь видит только отсутствие человека из общей группы;
- при отсутствии общих групп backend возвращает `403`.

### Фильтры и период

Backend поддерживает:

- `scope_type`
- `group_id`
- `year`
- `start_date`
- `end_date`
- `statuses`
- `categories`
- `q`

На UI сверху уже представлены готовые пресеты:

- `current_year`
- `current_month`
- `next_90_days`

По умолчанию WebApp показывает статусы:

- `approved`
- `pending`

`declined` по умолчанию скрыт.

### Безопасность WebApp

Проверки выполняются на backend:

- основной путь -> Telegram `initData`;
- разрешены заголовки `Authorization: tma ...` и `X-Telegram-Init-Data`;
- dev fallback по `X-Telegram-User-Id` работает только при `WEBAPP_ALLOW_DEV_FALLBACK=1`;
- совместимые каналы query/cookie/referer работают только при `WEBAPP_ALLOW_INITDATA_COMPAT=1`;
- `auth_date` в `initData` проверяется на возраст не старше 24 часов;
- на `/webapp/v1/*` действует rate limit по IP;
- на ответы ставятся security headers и CSP.

Frontend дополнительно не делает опасных вещей:

- не пишет `initData` в `localStorage`;
- не кладет `initData` в cookies;
- не передает `initData` в query string API-запросов;
- шлет auth контекст только в заголовках.

## Операционная CLI-панель

Единая точка входа:

```bash
python manage.py
# или
./manage
```

Без аргументов запускается интерактивное меню.

### Подкоманды CLI

- `menu`
- `status`
- `run`
- `service`
- `smoke`
- `backup`
- `governance`
- `broadcast`
- `alerts`
- `monitor`

### `run`

Компоненты:

- `bot`
- `webapp`
- `notify-once`

Поддерживаются:

- `--mode foreground`
- `--mode background`
- `--action start`
- `--action status`
- `--action stop`

Фоновые логи и PID:

- `.runtime/logs/*.log`
- `.runtime/pids/*.pid`

Остановка фонового процесса защищена дополнительной сверкой PID с `cmdline` процесса.

### `service`

Alias-цели:

- `bot`
- `webapp`
- `notify-service`
- `notify-timer`
- `backup-service`
- `backup-timer`
- `monitor-service`
- `monitor-timer`
- `cloudflared`
- `nginx`

Действия:

- `status`
- `start`
- `stop`
- `restart`
- `enable`
- `disable`

Поддерживаются `--scope user|system`.

### `smoke`

Проверяет базовый URL WebApp. Успешным считается поведение, при котором `/webapp/v1/me` без auth контекста отвечает `401` или `429`.

Если `--url` не указан, CLI использует:

- `WEBAPP_URL` из окружения, если он задан;
- иначе `http://127.0.0.1:8080/webapp`.

### `backup`

Поддерживаются:

- `create`
- `list`
- `verify`
- `restore`
- `prune`
- `usage`
- `schedule-enable`
- `schedule-disable`
- `schedule-status`
- `schedule-run`

Поведение:

- backup создаются в `backups/`;
- при `restore` можно автоматически создать safety backup текущей БД;
- есть disk guardrails `ok|warning|critical`;
- при `critical` backup и restore блокируются;
- planner пишет `telegram_bot_backup.service` и `telegram_bot_backup.timer` в user/system `systemd` директорию.

### `broadcast`

Фактическая отправка делегируется в `broadcast.py`.

Источники текста:

- `--text`
- `--file`
- `--changelog-latest [PATH]`

Аудитории:

- `all`
- `approved`
- `group:<id>`
- `superadmins`
- `group_admins`

Защита от случайной рассылки:

- реальная отправка требует `--confirm`;
- dry-run работает без токена.

### `alerts`

Подкоманды:

- `contacts list`
- `contacts add --id <telegram_id>`
- `contacts remove --id <telegram_id>`
- `test --message '...'`
- `event --unit <name> --scope user|system`

Контакты хранятся в `.runtime/ops_contacts.json`.

### `monitor`

Поддерживаются:

- `check`
- `schedule-enable`
- `schedule-disable`
- `schedule-status`
- `schedule-run`
- `events-enable`
- `events-disable`
- `events-status`

`monitor check` формирует инциденты по:

- bot;
- webapp;
- `telegram_bot_notify.timer`;
- диску backup volume;
- failed backup service;
- failed monitor service;
- опционально `nginx.service`.

Дополнительно:

- есть anti-spam state в `.runtime/monitor_state.json`;
- `events-enable` разворачивает template unit `telegram_bot_event_alert@.service` и `OnFailure` drop-in'ы;
- список unit'ов можно задать через alias или CSV service-unit'ов.

### `governance`

Поддерживаются:

- `checks`
- `checklist`

`checks` выполняет:

- локальную проверку наличия `.github/workflows/security-gate.yml`;
- проверку branch protection через `gh api`, если `gh` установлен и remote распознан как GitHub.

## Deploy-артефакты

### EnvironmentFile

- `deploy/env/telegram_bot.env.example`

### Nginx

- `deploy/nginx/telegram_webapp.conf.example`

Этот шаблон проксирует:

- `/webapp`
- `/webapp/static/`
- `/webapp/v1/`

### `systemd` шаблоны

User:

- `deploy/systemd-user/telegram_bot.service.example`
- `deploy/systemd-user/telegram_webapp.service.example`
- `deploy/systemd-user/telegram_bot_notify.service`
- `deploy/systemd-user/telegram_bot_notify.timer`

System:

- `deploy/systemd/telegram_bot.service.example`
- `deploy/systemd/telegram_webapp.service.example`

### `deploy/setup.sh`

Скрипт реально делает следующее:

- готовит `.venv`;
- ставит pip-зависимости;
- опционально ставит dev-зависимости;
- копирует user unit'ы ежедневных уведомлений;
- включает `telegram_bot_notify.timer`;
- опционально устанавливает system service только для `telegram_bot.service`.

WebApp service этот скрипт автоматически не разворачивает.

## Тесты

Основной раннер:

```bash
./.venv/bin/python -m unittest discover -s tests
```

Что покрыто тестами:

- Telegram flow и role/menu logic;
- WebApp ACL и validation;
- WebApp security headers и auth transport;
- ops CLI;
- broadcast;
- backup planner и monitor alerts;
- use case слои и SQL-репозитории.

Security gate:

```bash
./scripts/security_gate.sh
```

Он запускает:

- focused security tests;
- полный `unittest discover`;
- static checks против опасного логирования и опасного хранения `initData`.

CI workflow:

- `.github/workflows/security-gate.yml`
- триггеры -> `push` и `pull_request` в `main`.

## Карта модулей

### `app/entrypoints/`

- запуск приложений;
- не содержит доменную логику.

### `app/config/`

- bootstrap env-файлов;
- чтение строк, чисел, bool;
- fail-fast для `TOKEN`.

### `app/db/` и `app/repositories/`

- SQL-слой и репозиторные фасады;
- часть старых импортов продолжает жить через shim `db_repo.py`.

### `app/use_cases/`

- бизнес-логика отсутствий;
- модерация;
- пересечения;
- текстовые представления;
- CSV/XLSX export helpers.

### `app/webapp/`

- `api.py` -> маршруты `aiohttp`;
- `auth.py` -> проверка `initData`;
- `http.py` -> headers и rate limit middleware;
- `validation.py` -> parse/validate query parameters;
- `service.py` -> ACL и payload сборка;
- `export.py` -> XLSX export.

### `app/ops/`

- CLI parser;
- interactive menu;
- backup и planner;
- status/service helpers;
- monitoring и alerts;
- governance checks;
- broadcast delegation.

### Telegram UI-слой

- `handlers/`
- `core.py`
- `keyboards.py`
- `texts.py`
- `utils.py`

## Схема базы данных

SQLite-файл по умолчанию -> `bot_database.db`.

### `users`

- `telegram_id` PK
- `username`
- `fullname`
- `is_approved`
- `is_admin`
- `last_group_id`

### `absences`

- `id` PK
- `user_id`
- `category`
- `start_date`
- `end_date`
- `comment`
- `status`

### `logs`

- `id` PK
- `action_time`
- `user_id`
- `action`

### `edit_requests`

- `id` PK
- `abs_id`
- `new_cat`
- `new_sd`
- `new_ed`
- `new_comment`
- `user_id`

### `groups`

- `id` PK
- `name`
- `created_at`
- `created_by`

### `group_memberships`

- составной PK `user_id + group_id`
- `role` -> `member | viewer | admin`
- `created_at`
- `created_by`

### `group_requests`

- `id` PK
- `user_id`
- `group_id`
- `type` -> `join | leave`
- `status` -> `pending | approved | declined`
- `requested_at`
- `reviewed_at`
- `requested_by`
- `reviewed_by`

### `group_role_requests`

- `id` PK
- `user_id`
- `group_id`
- `target_role` -> сейчас используется `viewer`
- `status`
- `requested_at`
- `reviewed_at`
- `requested_by`
- `reviewed_by`

### `superadmin_notification_prefs`

- `user_id` PK
- `mode` -> `global | group_only | selected_groups`
- `updated_at`

### `superadmin_notification_groups`

- составной PK `user_id + group_id`

## Известные ограничения и технический долг

- `config.py` пока обязателен, потому что проект еще не полностью ушел от прямых импортов `config`.
- `DB_NAME` пока не централизован в одном settings-layer.
- Корневые shim-модули сохранены ради обратной совместимости и старых тестов/импортов.
- Часть deploy-потока все еще опирается на legacy entrypoint'ы в корне репозитория, хотя основная реализация уже живет в `app/*`.
