# Документация бота

## Назначение

Бот помогает фиксировать отсутствия сотрудников, согласовывать их и вести историю
заявок в SQLite. Поддерживаются группы, наблюдатели групп, администраторы групп
и суперадмины.

## Роли и состояния

Состояния пользователя:
- **не зарегистрирован** — записи в `users` нет;
- **ожидает одобрения** — `is_approved=0`;
- **одобрен** — `is_approved=1`.

Роли:
- **суперадмин** — глобальная роль (`is_admin=1`), видит все группы и всех пользователей.
- **администратор группы** — управляет только своей группой.
- **наблюдатель группы** — работает в своей группе в режиме чтения (без согласований и изменений).
- **пользователь** — работает в рамках групп, где состоит.

Если у пользователя **нет одобренной группы**, доступен только раздел «Группы»
(подача заявки на вступление).

## Регистрация и вступление в группу

1) Пользователь жмет `/start` и «Зарегистрироваться».
2) Указывает ФИО.
3) Админ одобряет/отклоняет регистрацию.
4) После одобрения пользователь подает заявку в группу.
5) Админ группы или суперадмин утверждает/отклоняет вступление.

## Рабочая группа

- Админ группы, если групп несколько, выбирает **рабочую группу**.
- Суперадмин может выбрать группу для фильтрации или переключиться в **глобальный** режим.
- В главном меню суперадмина кнопка вида **«Фильтр: ...»** всегда показывает
  активный контекст.
- Кнопка/команда «Текущая группа» показывает активную рабочую группу.

## Меню и функции

### Пользователь
- **Мои отсутствия**
  - Добавить отсутствие
  - Мои заявки (просмотр/изменение/удаление одобренных)
- **Группы**
  - Мои группы
  - Стать наблюдателем (заявка на read-only роль в выбранной группе)
  - Запроситься в группу
  - Выйти из группы
- **Для другого**
  - Добавить отсутствие другому пользователю

Если пересекаетесь с отсутствиями других людей, бот показывает пересечения.
Для **своего отсутствия** требуется подтверждение перед отправкой заявки.

### Администратор группы
- **Мои отсутствия** (как у пользователя)
- **Заявки в группу**
  - Заявки на вступление
  - Заявки на выход
  - Заявки на роль
- **Пользователи группы**
  - Список пользователей
  - Список администраторов группы
  - Назначить наблюдателя / Снять наблюдателя
  - Удалить пользователя из группы
- **Управление отсутствиями группы**
  - Заявки на отсутствие (pending)
  - Показать отсутствия пользователя
  - Изменить/удалить отсутствие пользователя
  - Добавить отсутствие другому пользователю
  - Выгрузить отсутствия в CSV
  - Отсутствия на сегодня
- **Группы**
  - Мои группы
  - Стать наблюдателем
  - Запроситься в группу / Выйти из группы
  - Текущая группа / Сменить группу

Админ группы может согласовывать отсутствия только **в своей группе**.

Ежедневные уведомления:
- получает сводку по заявкам на вступление в группу и заявкам на отсутствие.

### Наблюдатель группы
- **Мои отсутствия** (как у пользователя)
- **Заявки в группу** (только просмотр)
  - Заявки на вступление
  - Заявки на выход
  - Заявки на роль
- **Пользователи группы** (только просмотр)
  - Список пользователей
  - Список администраторов группы
- **Отсутствия группы** (только просмотр)
  - Заявки на отсутствие
  - Отсутствия сотрудника
  - Выгрузить отсутствия в CSV
  - Отсутствия на сегодня
- **Группы**
  - Мои группы
  - Стать наблюдателем
  - Текущая группа / Сменить группу (если групп несколько)

Наблюдатель не может:
- согласовывать/отклонять заявки;
- менять роли и состав группы;
- добавлять/изменять/удалять отсутствия других пользователей.

### Суперадмин
- **Мои отсутствия** (как у пользователя)
- **Управление пользователями**
  - Список пользователей
  - Список запросов (регистрация)
  - Изменить имя пользователя
  - Показать @username
  - Удалить пользователя из бота
- **Управление группами**
  - Создать / Удалить группу
  - Список групп
  - Список пользователей группы
  - Назначить админа / Снять админа группы
  - Назначить наблюдателя / Снять наблюдателя
  - Добавить / Удалить пользователя из группы
  - Заявки в группу
- **Управление отсутствиями**
  - Заявки на отсутствие (pending)
  - Показать отсутствия пользователя
  - Изменить / Удалить отсутствие пользователя
  - Добавить отсутствие другому пользователю
  - Выгрузить отсутствия в CSV
- **Отсутствия на сегодня**
- **Управление суперадминами**
  - Добавить / Отозвать права суперадмина
  - Список суперадминистраторов
- **Фильтр по группе**
  - Текущая группа / Сменить группу / Глобально

Суперадмин видит все группы и может согласовывать отсутствие любого пользователя.

Ежедневные уведомления:
- получает сводку по новым заявкам на регистрацию в боте;
- получает сводку по групповым заявкам в рамках текущего режима уведомлений
  (глобально или выбранная группа).

Важно:
- realtime и ежедневные уведомления суперадмина учитывают выбранный фильтр;
- пересечения в уведомлениях суперадмина также считаются в рамках активного фильтра.

## Отсутствия

Категории:
- `vacation` — Отпуск
- `sick` — Больничный
- `dayoff` — DayOff
- `other` — Другое

Статусы заявок:
- `pending` — ожидает решения администратора.
- `approved` — одобрено.
- `declined` — отклонено.

Пользователь может **изменять/удалять только approved‑заявки** (через запрос).

## Команды

- `/start` — приветствие и меню по роли.
- `/approve <telegram_id>` — ручное одобрение пользователя (суперадмин).
- `/decline <telegram_id>` — ручное отклонение пользователя (суперадмин).
- `/refresh_menu` — обновить меню у всех одобренных пользователей (суперадмин).

## WebApp (read-only пересечения)

Отдельный интерфейс визуализации пересечений, не заменяющий основной чат-бот.
Пользователь открывает его кнопкой **«Пересечения (WebApp)»** из главного меню.
После этого бот отправляет inline-кнопку **«Открыть WebApp»** (основной путь запуска).

Запуск backend:
```
WEBAPP_HOST=127.0.0.1 WEBAPP_PORT=8080 python webapp_api.py
```

Доступные endpoint'ы:
- `GET /webapp/v1/me` — профиль, роль, доступные scope/группы;
- `GET /webapp/v1/overlaps` — интервалы отсутствий + дневная нагрузка (`daily_load`);
- `GET /webapp/v1/absence/{id}` — детали выбранного отсутствия;
- `GET /webapp/v1/export/xlsx` — выгрузка текущего вида в XLSX.

Фильтры WebApp:
- scope (`global` / `group` / `superadmins`, по ACL роли);
- группа (для scope `group`);
- период (`current_year`, `current_month`, `next_90_days`);
- статусы, категории, текстовый поиск.

Подсветка конфликтов:
- параметр **«Конфликт от»** задает порог отсутствующих сотрудников в день;
- дни, где `absent_users >= threshold`, подсвечиваются по всей сетке.

Безопасность:
- production-режим: только проверка Telegram `initData`;
- dev fallback по заголовку `X-Telegram-User-Id` работает только при
  `WEBAPP_ALLOW_DEV_FALLBACK=1` (локальная разработка);
- каналы совместимости `initData` (query/cookie/referer) можно отключить
  через `WEBAPP_ALLOW_INITDATA_COMPAT=0` (рекомендуется для production);
- на `/webapp/v1/*` включен rate limit (по IP);
- публичный URL WebApp не должен отдавать данные без валидного `initData`.
- для части Telegram Desktop клиентов reply-кнопка `web_app` менее стабильна,
  поэтому рекомендуется запуск через inline-кнопку `web_app`.

Инфраструктурные требования:
- WebApp должен быть доступен по публичному HTTPS URL;
- поддерживаются 2 варианта публикации:
  - Nginx reverse proxy (`/webapp`, `/webapp/static/`, `/webapp/v1/`);
  - Cloudflare Tunnel (проксирование host -> `127.0.0.1:8080` без прямого входящего 443);
- домен должен быть задан в BotFather через `/setdomain`;
- тест и production рекомендуется разделять поддоменами
  (например, `bot-test.example.com` и `bot.example.com`).
- при Cloudflare Tunnel нельзя держать конфликтующие DNS-записи одного host
  (`A/AAAA/CNAME` одновременно).

Минимальный security baseline для production:
- `WEBAPP_ALLOW_DEV_FALLBACK=0`;
- `WEBAPP_ALLOW_INITDATA_COMPAT=0`;
- `WEBAPP_HOST=127.0.0.1` (backend доступен только локально);
- задан rate limit:
  - `WEBAPP_RATE_LIMIT_MAX_REQUESTS` (по умолчанию `120`);
  - `WEBAPP_RATE_LIMIT_WINDOW_SEC` (по умолчанию `60`);
- внешний `:8080` закрыт;
- включены security headers на edge-слое (Nginx/Cloudflare);
- без `initData` API должен возвращать `401/403`;
- при burst-нагрузке API должен возвращать `429`.

Эти параметры можно задавать как в `config.py`, так и через env-переменные
(env имеет приоритет).

Рекомендуемый production-подход:
- секреты (`TOKEN`) задаются через `EnvironmentFile` в systemd;
- не-секретные runtime-настройки (`WEBAPP_*`, `DB_NAME`) остаются в `config.py`;
- `config.py` используется как локальный fallback для разработки;
- секреты (`TOKEN`) не хранятся в репозитории.

Шаблоны EnvironmentFile:
- `deploy/env/telegram_bot.env.example`

Systemd-шаблоны:
- рекомендуемый вариант (user services):
  - `deploy/systemd-user/telegram_bot.service.example`
  - `deploy/systemd-user/telegram_webapp.service.example`
  - `deploy/systemd-user/telegram_bot_notify.service`
- альтернативно (system services):
  - `deploy/systemd/telegram_bot.service.example`
  - `deploy/systemd/telegram_webapp.service.example`

Перед релизом запускается security gate:
```
./scripts/security_gate.sh
```

## Операционная CLI-панель

Единая точка входа:
```
python manage.py
# или
./manage
```

Источники `TOKEN` для CLI/скриптов (по приоритету):
- переменная окружения процесса;
- путь из `TELEGRAM_BOT_ENV_FILE`;
- `~/.config/telegram_bot/telegram_bot.env`;
- `/etc/telegram_bot/telegram_bot.env`;
- `./.env`.
- `config.py` (fallback для локальной разработки).

Без аргументов запускается интерактивное меню:
- статус компонентов;
- локальные компоненты без systemd (запуск в фоне/остановка/статус + foreground);
- управление systemd unit'ами;
- рассылка с wizard-потоком (источник, аудитория, предпросмотр, подтверждение `SEND`);
- smoke WebApp;
- backup БД (create/list/verify/restore/prune/usage + scheduler);
- мониторинг и тех-уведомления (контакты, check, monitor timer; в menu техадмины выбираются из списка пользователей);
- событийные алерты через systemd `OnFailure` (enable/disable/status).
- во всех разделах есть явный пункт возврата в главное меню.

Командный режим (для автоматизации):
```
python manage.py status
python manage.py run bot --mode background
python manage.py run bot --action status
python manage.py run bot --action stop
python manage.py run bot --mode foreground
python manage.py service bot restart --scope user
python manage.py smoke --url https://bot-test.justasite.cc/webapp
python manage.py backup create
python manage.py governance checks --branch main
python manage.py governance checklist
python manage.py backup restore --path backups/bot_database_YYYYMMDD_HHMMSS.db
python manage.py backup prune --retain 20
python manage.py backup usage
python manage.py backup schedule-enable --time 03:30 --retain 20 --scope user
python manage.py backup schedule-status --scope user
python manage.py monitor check --notify
python manage.py monitor schedule-enable --interval 10 --scope user
python manage.py monitor events-enable --scope user --units bot,webapp
python manage.py monitor events-status --scope user --units bot,webapp
python manage.py alerts contacts add --id 123456789
python manage.py alerts test --message "Тест тех-уведомлений"
```

Ежедневный runbook оператора:
```
# 1) Проверить состояние
python manage.py status
python manage.py monitor check

# 2) Проверить/выполнить backup
python manage.py backup usage
python manage.py backup create
python manage.py backup verify

# 3) При необходимости — сервисная рассылка
python manage.py broadcast --audience approved --changelog-latest --dry-run
python manage.py broadcast --audience approved --changelog-latest --confirm
```

### Рассылка

Команда:
```
python manage.py broadcast ...
```

`broadcast.py` сохранен как совместимый legacy-скрипт.

Поддерживаемые аудитории:
- `all` — все пользователи из БД;
- `approved` — только одобренные;
- `group:<id>` — участники конкретной группы;
- `superadmins` — суперадмины;
- `group_admins` — администраторы групп.

Основные параметры:
- `--text "..."` или `--file <path>` — источник текста;
- `--changelog-latest [PATH]` — взять только верхний релизный блок из CHANGELOG
  (по умолчанию `CHANGELOG.md`);
- `--dry-run` — только показать получателей, без отправки;
- `--confirm` — обязательное подтверждение для реальной отправки;
- `--limit N` — ограничить число получателей;
- `--delay SEC` — пауза между отправками.

Пример:
```
python manage.py broadcast --audience approved --file CHANGELOG.md --dry-run
python manage.py broadcast --audience approved --changelog-latest --confirm
```

### Backup-команды

- `python manage.py backup create` — создать backup текущей БД.
- `python manage.py backup list` — показать список backup-файлов.
- `python manage.py backup verify [--path FILE]` — проверить integrity (`PRAGMA integrity_check`).
- `python manage.py backup restore --path FILE` — восстановить БД из backup (с созданием safety backup текущей БД).
- `python manage.py backup prune --retain N` — удалить старые backup, оставить последние `N`.
- `python manage.py backup usage` — показать свободное место на томе backup.
- `python manage.py backup schedule-enable --time HH:MM --retain N --scope user|system` — включить backup timer.
- `python manage.py backup schedule-status --scope user|system` — показать статус backup timer.
- `python manage.py backup schedule-disable --scope user|system` — отключить backup timer.
- `python manage.py backup schedule-run --scope user|system` — запустить backup job вручную.

### Monitor/alerts-команды

- `python manage.py alerts contacts list` — список техадминов.
- `python manage.py alerts contacts add --id <telegram_id>` — добавить техадмина.
- `python manage.py alerts contacts remove --id <telegram_id>` — удалить техадмина.
- `python manage.py alerts test --message "..."` — отправить тестовое тех-уведомление.
- `python manage.py monitor check [--notify]` — проверка инцидентов (bot/webapp/systemd/disk/backup).
- `python manage.py monitor schedule-enable --interval N --scope user|system` — включить monitor timer.
- `python manage.py monitor schedule-status --scope user|system` — статус monitor timer.
- `python manage.py monitor schedule-disable --scope user|system` — отключить monitor timer.
- `python manage.py monitor schedule-run --scope user|system` — запустить monitor job вручную.
- `python manage.py monitor events-enable --scope user|system [--units CSV]` — включить событийные алерты (`OnFailure` drop-in + template unit).
- `python manage.py monitor events-status --scope user|system [--units CSV]` — статус событийных алертов.
- `python manage.py monitor events-disable --scope user|system [--units CSV]` — отключить событийные алерты.

Опциональный мониторинг nginx:
- в `config.py`:
  - `MONITOR_NGINX_ENABLED = True` — включить проверку `nginx.service` в monitor check;
  - `MONITOR_NGINX_UNIT = "..."` — переопределить имя unit (по умолчанию `nginx.service`).
- env-переменные с теми же именами работают как override поверх `config.py`.

### Governance-команды

- `python manage.py governance checks --branch main` — проверить release-gates
  (локальный workflow + branch protection через `gh`, если доступен).
- `python manage.py governance checklist` — вывести обязательный чеклист перед релизом.

Правило ведения CHANGELOG для совместимости с `--changelog-latest`:
- каждый релиз оформляется отдельным заголовком `## ...`;
- новый релиз добавляется в начало файла;
- исторические блоки остаются ниже без удаления.

## Ежедневные уведомления

Отправка сводок запускается отдельной задачей (например, через user‑timer systemd):
файлы в `deploy/systemd-user/`. Уведомления отправляются только при наличии заявок.

## RFC и архив

- Реализованный RFC по read-only WebApp перенесен в архив: `docs/archive/WEBAPP_READONLY_RFC.md`.
- Закрытые RFC по безопасности и рефакторингу структуры перенесены в архив:
  - `docs/archive/SECURITY_HARDENING_RFC.md`
  - `docs/archive/PROJECT_STRUCTURE_REFACTOR_RFC.md`
- Завершенный RFC операционной панели: `docs/rfc/OPERATIONS_CLI_PANEL_RFC.md`.

## Карта модулей (актуальная)

Слой приложения:
- `app/entrypoints/` — запуск приложений (`bot_main.py`, `webapp_main.py`, `notifications_main.py`);
- `app/config/settings.py` — чтение env/config параметров;
- `app/db/` и `app/repositories/` — SQL-слой и фасады репозиториев;
- `app/use_cases/` — бизнес-логика (сценарии отсутствий, модерация, пересечения, отчеты/экспорты);
- `app/ops/` — операционный CLI-слой (`cli.py`, `menu.py`, `status_ops.py`, `service_ops.py`, `smoke_ops.py`, `broadcast_ops.py`, `backup_ops.py`, `backup_planner_ops.py`, `alerts_ops.py`, `monitor_ops.py`, `systemd_units.py`);
- `app/webapp/`:
  - `api.py` — HTTP endpoint'ы и сборка `aiohttp` app;
  - `auth.py` — валидация Telegram initData и auth-context;
  - `http.py` — middleware безопасности и rate-limit;
  - `validation.py` — парсинг/валидация query/path параметров;
  - `service.py` — read-only ACL и формирование payload;
  - `export.py` — формирование XLSX.

Telegram-слой:
- `handlers/` — обработчики команд/кнопок;
- `core.py`, `keyboards.py`, `texts.py`, `utils.py` — общий доменный и UI-слой.

Совместимость (shim-модули на корне):
- `bot.py`, `webapp_api.py`, `webapp_readonly.py`, `webapp_export.py`,
  `settings.py`, `db_repo.py`.
- Эти файлы сохранены для обратной совместимости импорта/запуска; новая реализация находится в `app/*`.

## База данных

SQLite файл по умолчанию: `bot_database.db`.

Таблицы:

### users
- `telegram_id` (PK)
- `username`
- `fullname`
- `is_approved`
- `is_admin`
- `last_group_id`

### absences
- `id` (PK)
- `user_id` (FK -> users.telegram_id)
- `category`
- `start_date` (ISO, `YYYY-MM-DD`)
- `end_date` (ISO, `YYYY-MM-DD`)
- `comment`
- `status`

### groups
- `id` (PK)
- `name`
- `created_at`
- `created_by`

### group_memberships
- `user_id` (FK -> users.telegram_id)
- `group_id` (FK -> groups.id)
- `role` (`member` / `viewer` / `admin`)
- `created_at`
- `created_by`

### group_requests
- `id` (PK)
- `user_id`
- `group_id`
- `type` (`join` / `leave`)
- `status` (`pending` / `approved` / `declined`)
- `requested_at` / `reviewed_at`
- `requested_by` / `reviewed_by`

### group_role_requests
- `id` (PK)
- `user_id`
- `group_id`
- `target_role` (`viewer`)
- `status` (`pending` / `approved` / `declined`)
- `requested_at` / `reviewed_at`
- `requested_by` / `reviewed_by`

### superadmin_notification_prefs
- `user_id` (PK)
- `mode` (`global` / `group_only` / `selected_groups`)
- `updated_at`

### superadmin_notification_groups
- `user_id`
- `group_id`

### logs
Журнал действий (время, пользователь, действие).

### edit_requests
Запросы на изменение заявок (новые значения, user_id).

## Логи

Ключевые действия пишутся в таблицу `logs` и в консоль.
