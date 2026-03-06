# WhereAreYou_Bot

Telegram-бот для учета отсутствий сотрудников. Проект уже не ограничивается только чат-ботом: в репозитории есть основной Telegram runtime, read-only WebApp для визуализации пересечений, worker ежедневных уведомлений и операционная CLI-панель для сопровождения.

## Что есть в проекте

- `bot.py` -> Telegram-бот на `aiogram`.
- `webapp_api.py` -> `aiohttp` backend для WebApp.
- `notifications.py` -> разовый запуск ежедневных уведомлений.
- `manage.py` / `./manage` -> операционная CLI-панель.
- `app/` -> актуальная реализация модулей.
- корневые файлы `bot.py`, `webapp_api.py`, `webapp_readonly.py`, `webapp_export.py`, `settings.py`, `db_repo.py` -> compatibility shim'ы для старых импортов и сценариев запуска.

## Быстрый старт

### 1. Установить зависимости

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Опционально для разработки:

```bash
pip install -r requirements-dev.txt
```

Зависимости CLI, бота и WebApp общие. До установки `requirements.txt` даже `manage.py --help` может не запуститься.

### 2. Создать локальный `config.py`

```bash
cp config_example.py config.py
```

Это по-прежнему обязательный шаг. В проекте остались legacy-модули, которые импортируют `config` напрямую, поэтому одного `EnvironmentFile` без `config.py` сейчас недостаточно.

### 3. Заполнить конфигурацию

Минимум для локального запуска бота:

- задать `TOKEN` в `config.py` или через окружение;
- оставить `DB_NAME = "bot_database.db"`, если нет явной причины переносить БД;
- указать `WEBAPP_URL`, если нужна кнопка `Пересечения (WebApp)` в меню.

### 4. Запустить компоненты

Telegram-бот:

```bash
python bot.py
```

WebApp backend:

```bash
python webapp_api.py
```

Разовая отправка ежедневных уведомлений:

```bash
python notifications.py
```

SQLite-схема создается при старте через `database.init_db()`.

## Конфигурация

### Источники настроек

Централизованное чтение через `app.config.settings` использует такой порядок:

1. переменные окружения процесса;
2. путь из `TELEGRAM_BOT_ENV_FILE`;
3. `~/.config/telegram_bot/telegram_bot.env`;
4. `/etc/telegram_bot/telegram_bot.env`;
5. `./.env`;
6. `config.py` как локальный fallback.

Важно:

- этот bootstrap работает только для параметров, которые читаются через `app.config.settings` или `os.getenv`;
- часть legacy-кода до сих пор читает значения напрямую из `config.py`;
- поэтому `config.py` должен существовать даже в production.

### Ключевые параметры

`config.py` / env:

- `TOKEN` -> токен бота.
- `DB_NAME` -> путь к SQLite-файлу.
- `WEBAPP_URL` -> публичный URL вида `https://example.com/webapp`.
- `WEBAPP_HOST`, `WEBAPP_PORT` -> bind WebApp backend.
- `WEBAPP_ALLOW_DEV_FALLBACK` -> разрешить dev auth по `X-Telegram-User-Id`.
- `WEBAPP_ALLOW_INITDATA_COMPAT` -> разрешить query/cookie/referer-каналы initData.
- `WEBAPP_RATE_LIMIT_MAX_REQUESTS`, `WEBAPP_RATE_LIMIT_WINDOW_SEC` -> rate limit для `/webapp/v1/*`.
- `MONITOR_NGINX_ENABLED`, `MONITOR_NGINX_UNIT` -> опциональная проверка `nginx` в `manage.py monitor check`.

### Текущие ограничения по `DB_NAME`

Путь к БД пока не централизован полностью.

- Основной runtime инициализирует схему через `database.py`, где безопасный дефолт -> `bot_database.db`.
- SQL-репозитории читают `DB_NAME` из `config.py`.
- Backup/restore в ops-слое ориентируются на `DB_NAME` из окружения или на дефолт `bot_database.db`.

Практический вывод:

- безопасный путь -> оставить `DB_NAME = "bot_database.db"`;
- если база переносится в другое место, проверьте, что bot runtime, WebApp runtime и backup-команды работают с одним и тем же файлом.

## Роли и основные сценарии

Поддерживаются:

- пользователь;
- наблюдатель группы;
- администратор группы;
- суперадмин.

Основные функции:

- регистрация и ручное одобрение пользователя;
- группы, заявки на вступление и выход;
- роль `наблюдатель` с доступом только на чтение;
- заявки на отсутствие с согласованием;
- добавление отсутствия за другого сотрудника;
- показ пересечений при создании заявки;
- WebApp для визуализации пересечений;
- экспорт отсутствий в CSV из бота и XLSX из WebApp;
- ежедневные сводки и сервисные рассылки.

Подробная карта ролей, меню и прав лежит в `DOCUMENTATION.md`.

## WebApp

WebApp запускается как отдельный backend и открывается из бота через inline-кнопку `Открыть WebApp`.

Почему именно так:

- reply-кнопка `web_app` на части Telegram Desktop клиентов менее стабильна;
- inline-кнопка дает более надежный `initData`.

### Что умеет WebApp

- scope `group` для обычных пользователей, наблюдателей и админов группы;
- scope `global`, `group`, `superadmins` для суперадмина;
- пресеты периода `Текущий год`, `Текущий месяц`, `Следующие 90 дней`;
- фильтры по статусам, категориям и поиску;
- подсветка конфликтных дней по порогу `Конфликт от`;
- детализация отсутствия по клику;
- экспорт текущего представления в XLSX.

### Backend endpoints

- `GET /webapp`
- `GET /webapp/v1/me`
- `GET /webapp/v1/overlaps`
- `GET /webapp/v1/absence/{absence_id}`
- `GET /webapp/v1/export/xlsx`

### Локальная отладка WebApp

Запуск backend:

```bash
source .venv/bin/activate
python webapp_api.py
```

Для браузерной локальной проверки без Telegram нужны одновременно:

- валидный `TOKEN` в окружении или `config.py`;
- `WEBAPP_ALLOW_DEV_FALLBACK=1`;
- существующий пользователь в БД.

Пример:

```bash
WEBAPP_ALLOW_DEV_FALLBACK=1 python webapp_api.py
```

После этого можно открыть:

```text
http://127.0.0.1:8080/webapp?dev_user_id=<telegram_id>
```

или проверить API напрямую:

```bash
curl -H 'X-Telegram-User-Id: <telegram_id>' 'http://127.0.0.1:8080/webapp/v1/me'
```

### Production baseline для WebApp

- публичный HTTPS URL;
- домен зарегистрирован у BotFather через `/setdomain`;
- `WEBAPP_ALLOW_DEV_FALLBACK=0`;
- `WEBAPP_ALLOW_INITDATA_COMPAT=0`;
- backend слушает `127.0.0.1`;
- внешний доступ к `:8080` закрыт;
- на edge настроены security headers;
- API без валидного auth контекста возвращает `401/403`;
- на burst-нагрузке `/webapp/v1/*` возвращает `429`.

Шаблоны для деплоя:

- `deploy/nginx/telegram_webapp.conf.example`
- `deploy/systemd-user/telegram_webapp.service.example`
- `deploy/systemd/telegram_webapp.service.example`
- `deploy/env/telegram_bot.env.example`

## Операционная CLI-панель

Единая точка входа:

```bash
python manage.py
# или
./manage
```

Без аргументов запускается интерактивное меню. В командном режиме доступны подкоманды:

- `status`
- `run`
- `service`
- `smoke`
- `backup`
- `governance`
- `broadcast`
- `alerts`
- `monitor`

### Локальный запуск компонентов без `systemd`

Компоненты для `manage.py run`:

- `bot`
- `webapp`
- `notify-once`

Примеры:

```bash
python manage.py run bot --mode foreground
python manage.py run bot --mode background
python manage.py run bot --action status
python manage.py run bot --action stop
```

Фоновые PID и логи хранятся в `.runtime/pids` и `.runtime/logs`.

### Управление `systemd`

Alias-цели для `manage.py service`:

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

Примеры:

```bash
python manage.py service bot status --scope user
python manage.py service webapp restart --scope user
python manage.py service nginx status --scope system
```

### Backup

Основные команды:

```bash
python manage.py backup create
python manage.py backup list
python manage.py backup verify
python manage.py backup restore --path backups/<file>.db
python manage.py backup prune --retain 20
python manage.py backup usage
```

Планировщик backup создает chain `create -> verify -> prune`.

```bash
python manage.py backup schedule-enable --time 03:30 --retain 20 --scope user
python manage.py backup schedule-status --scope user
python manage.py backup schedule-run --scope user
python manage.py backup schedule-disable --scope user
```

Backup-файлы лежат в `backups/`.

### Мониторинг и тех-уведомления

`monitor check` отслеживает:

- bot;
- webapp;
- `telegram_bot_notify.timer`;
- disk guardrails для backup volume;
- `telegram_bot_backup.service` в состоянии `failed`;
- `telegram_bot_monitor.service` в состоянии `failed`;
- опционально `nginx.service`.

Команды:

```bash
python manage.py monitor check
python manage.py monitor check --notify
python manage.py monitor schedule-enable --interval 10 --scope user
python manage.py monitor events-enable --scope user --units bot,webapp
python manage.py monitor events-status --scope user --units bot,webapp
```

Контакты техадминов хранятся в `.runtime/ops_contacts.json`.

```bash
python manage.py alerts contacts list
python manage.py alerts contacts add --id 123456789
python manage.py alerts contacts remove --id 123456789
python manage.py alerts test --message 'Тест тех-уведомлений'
```

Антиспам включен: при неизменившемся инциденте повторное уведомление не отправляется.

### Рассылка

Основной интерфейс рассылки -> `manage.py broadcast`. Legacy-скрипт `broadcast.py` сохранен для совместимости.

Поддерживаемые аудитории:

- `all`
- `approved`
- `group:<id>`
- `superadmins`
- `group_admins`

Примеры:

```bash
python manage.py broadcast --audience approved --changelog-latest --dry-run
python manage.py broadcast --audience approved --changelog-latest --confirm
python manage.py broadcast --audience group:3 --file ./message.md --dry-run
```

Без `--confirm` реальная отправка заблокирована.

### Smoke и governance

```bash
python manage.py smoke --url https://example.com/webapp
python manage.py governance checks --branch main
python manage.py governance checklist
```

`smoke` проверяет, что `/webapp/v1/me` без auth контекста закрыт кодом `401` или `429`.

## Deployment

### Быстрая заготовка

`deploy/setup.sh` делает только то, что реально заявлено в коде:

- создает `.venv` или симлинк на `venv`;
- ставит `requirements.txt`;
- при `--dev` ставит `requirements-dev.txt`;
- копирует user unit'ы ежедневных уведомлений;
- включает `telegram_bot_notify.timer`;
- при `--with-systemd` может установить system service только для `telegram_bot.service`.

Пример:

```bash
bash deploy/setup.sh --dev
```

### `systemd` шаблоны

User services:

- `deploy/systemd-user/telegram_bot.service.example`
- `deploy/systemd-user/telegram_webapp.service.example`
- `deploy/systemd-user/telegram_bot_notify.service`
- `deploy/systemd-user/telegram_bot_notify.timer`

System services:

- `deploy/systemd/telegram_bot.service.example`
- `deploy/systemd/telegram_webapp.service.example`

### EnvironmentFile

Шаблон:

- `deploy/env/telegram_bot.env.example`

Production practice:

- `TOKEN` держать во внешнем `EnvironmentFile`;
- `config.py` хранить локально и не коммитить;
- `WEBAPP_*` и `MONITOR_*` можно задавать через env или `config.py`;
- `config.py` все равно должен оставаться в deploy-окружении.

## Тесты и release gate

Основной раннер:

```bash
./.venv/bin/python -m unittest discover -s tests
```

Опционально через `pytest`:

```bash
pytest
```

Security gate:

```bash
./scripts/security_gate.sh
```

Он выполняет:

- focused security tests;
- полный `unittest discover`;
- статические проверки на утечки `initData` в логах и фронтенде.

CI workflow:

- `.github/workflows/security-gate.yml`
- запускается на `push` и `pull_request` для ветки `main`.

## Структура проекта

```text
app/
  config/        runtime settings bootstrap
  db/            SQL-реализация
  repositories/  фасады репозиториев
  use_cases/     доменные сценарии
  webapp/        backend WebApp
  ops/           операционная CLI и systemd helpers
  entrypoints/   реальные точки входа
handlers/        Telegram handlers
webapp_static/   frontend WebApp
deploy/          шаблоны deploy/systemd/nginx/env
tests/           автотесты
```

## Документация

- `DOCUMENTATION.md` -> подробное описание ролей, меню, WebApp, CLI и схемы БД.
- `CHANGELOG.md` -> пользовательские и технические изменения.
- `SECURITY.md` -> security policy и production baseline.
- `docs/archive/` -> закрытые RFC в архиве.
- `docs/rfc/OPERATIONS_CLI_PANEL_RFC.md` -> актуальный RFC по ops CLI. Этот файл намеренно не менялся в рамках актуализации документации.
