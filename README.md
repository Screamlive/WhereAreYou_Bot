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

2) Для локальной разработки создайте `config.py`:
```
cp config_example.py config.py
```

3) Запуск:
```
python bot.py
```

При первом запуске создается SQLite‑база `bot_database.db`.

## Конфигурация

Локальный файл `config.py`:
- `TOKEN` — токен бота от BotFather.
- `DB_NAME` — имя файла SQLite.
- `WEBAPP_URL` — публичный HTTPS URL WebApp (например, `https://example.com/webapp`).
- `WEBAPP_*` — параметры WebApp API и rate limit.

Важно: `database.py` использует имя базы по умолчанию `bot_database.db`.
Если меняете `DB_NAME`, синхронизируйте значение в `database.py`.

Production best practice:
- секреты (`TOKEN`) задаются через `EnvironmentFile` (systemd), а не через `config.py`;
- не-секретные параметры (`WEBAPP_*`, `DB_NAME`) хранятся в `config.py`;
- приоритет источников: `env` > `config.py`;
- `config.py` не хранится в git и используется как локальный fallback.

Пример файлов:
- `deploy/env/telegram_bot.env.example`

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
- далее бот присылает inline-кнопку **«Открыть WebApp»**;
- кнопка показывается, если задан `WEBAPP_URL` (в `config.py` или через env `WEBAPP_URL`).

Обязательные условия для Telegram WebApp в production:
- публичный HTTPS домен;
- домен прописан в BotFather через `/setdomain`;
- backend не выдает данные без валидного `initData`.

Нюанс Telegram Desktop:
- самый стабильный путь открытия — через inline-кнопку `web_app` от бота;
- прямой запуск WebApp как reply-кнопки может давать пустой `initData` в части desktop-клиентов.

Запуск backend WebApp:
```
source .venv/bin/activate
WEBAPP_HOST=127.0.0.1 WEBAPP_PORT=8080 python webapp_api.py
```

Открытие в браузере для локальной проверки (без Telegram):
```
WEBAPP_ALLOW_DEV_FALLBACK=1 python webapp_api.py
curl -H "X-Telegram-User-Id: <telegram_id>" "http://127.0.0.1:8080/webapp/v1/me"
```

Важно по безопасности:
- для production используется только Telegram `initData` (dev fallback выключен по умолчанию);
- каналы совместимости `initData` (query/cookie/referer) в production лучше отключать:
  `WEBAPP_ALLOW_INITDATA_COMPAT=0`;
- URL WebApp публичный, но запросы без валидного `initData` получают `401/403`;
- на `/webapp/v1/*` действует rate limit (по IP);
- для Telegram WebApp нужен HTTPS-домен и настройка домена через BotFather (`/setdomain`).

## Варианты публикации WebApp (production)

### Вариант A: Nginx + прямой DNS (A-запись)

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
WEBAPP_HOST=127.0.0.1 WEBAPP_PORT=8080 WEBAPP_ALLOW_DEV_FALLBACK=0 WEBAPP_ALLOW_INITDATA_COMPAT=0 python webapp_api.py
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

6) Задайте production-параметры через EnvironmentFile:
```
sudo install -d -m 755 /etc/telegram_bot
sudo install -m 600 -o <user> -g <user> deploy/env/telegram_bot.env.example /etc/telegram_bot/telegram_bot.env
# отредактируйте TOKEN (при необходимости DB_NAME можно оставить в config.py)
```

7) В BotFather для соответствующего бота:
```
/setdomain
bot-test.example.com
```

8) Перезапустите бота и WebApp API.

Примечание:
- `requirements-system.txt` содержит список системных пакетов для деплоя.

### Вариант B: Cloudflare Tunnel (без прямого входящего 443 на сервер)

Подходит, если 443 уже занят другим сервисом на сервере (например, Xray) или
не хотите светить origin через открытые web-порты.

1) Поднимите backend WebApp локально:
```
source .venv/bin/activate
WEBAPP_PORT=8080 WEBAPP_ALLOW_DEV_FALLBACK=0 WEBAPP_ALLOW_INITDATA_COMPAT=0 python webapp_api.py
```

2) Настройте Cloudflare Tunnel:
```
cloudflared tunnel login
cloudflared tunnel create telegram-webapp-test
cloudflared tunnel route dns telegram-webapp-test bot-test.example.com
```

3) Пример `/etc/cloudflared/config.yml`:
```
tunnel: telegram-webapp-test
credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: bot-test.example.com
    service: http://127.0.0.1:8080
  - service: http_status:404
```

4) Запустите tunnel как сервис:
```
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

5) Для этого же бота в BotFather:
```
/setdomain
bot-test.example.com
```

Важно:
- для одного host в DNS не должно быть конфликтующих записей (A/AAAA/CNAME одновременно);
- даже с tunnel доступ к данным защищается только backend-проверкой `initData`, не самим фактом HTTPS.

Systemd-шаблоны для production:
- рекомендуемый вариант (user services):
  - `deploy/systemd-user/telegram_bot.service.example`
  - `deploy/systemd-user/telegram_webapp.service.example`
- альтернативно (system services):
  - `deploy/systemd/telegram_bot.service.example`
  - `deploy/systemd/telegram_webapp.service.example`
- все используют `EnvironmentFile=/etc/telegram_bot/telegram_bot.env`.

## Security baseline перед прод-деплоем

Обязательный минимум:
- `WEBAPP_ALLOW_DEV_FALLBACK=0` в production;
- `WEBAPP_ALLOW_INITDATA_COMPAT=0` в production;
- `WEBAPP_HOST=127.0.0.1` (чтобы backend не слушал внешний интерфейс);
- настроен rate limit (`WEBAPP_RATE_LIMIT_MAX_REQUESTS`, `WEBAPP_RATE_LIMIT_WINDOW_SEC`);
- внешний доступ к `:8080` закрыт firewall/сетевой политикой;
- TLS и `/setdomain` настроены;
- бэкап БД создан и проверен.

Быстрые проверки:
```
# 1) Проверить bind WebApp API (ожидается 127.0.0.1:8080)
ss -lntp | rg 8080

# 2) Проверить, что без initData API не отдает данные
curl -i "https://bot-test.example.com/webapp/v1/me"

# 3) Проверить security headers на edge
curl -I "https://bot-test.example.com/webapp" | rg -i "content-security-policy|x-frame-options|x-content-type-options|referrer-policy|permissions-policy"

# 4) Проверить, что rate limit срабатывает (должен появиться 429)
for i in $(seq 1 150); do curl -s -o /dev/null -w "%{http_code}\n" "https://bot-test.example.com/webapp/v1/me"; done | sort | uniq -c
```

Security gate перед релизом:
```
./scripts/security_gate.sh
```

CI gate:
- workflow `security-gate` запускается на `pull_request` в `main` и на `push` в `main`:
  `.github/workflows/security-gate.yml`;
- рекомендуется включить branch protection для `main` с обязательным статус-чеком `security-gate`.

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

## Операционная CLI-панель

Есть единая точка управления:
```
python manage.py
# или
./manage
```

Примечание по секретам для локального CLI:
- поддерживаются источники `TOKEN` (в порядке приоритета): env процесса,
  `TELEGRAM_BOT_ENV_FILE`, `~/.config/telegram_bot/telegram_bot.env`,
  `/etc/telegram_bot/telegram_bot.env`, `./.env`, `config.py` (fallback).

По умолчанию откроется интерактивное меню с основными сценариями:
- статус компонентов;
- локальные компоненты без systemd (запуск в фоне/остановка/статус + foreground при необходимости);
- управление systemd-сервисами;
- рассылка (wizard: источник -> аудитория -> dry-run -> подтверждение `SEND`);
- smoke WebApp;
- backup БД (create/list/verify/restore/prune/usage + scheduler);
- мониторинг и тех-уведомления (контакты, check, monitor timer);
- событийные алерты через systemd `OnFailure` (enable/disable/status).
- во всех разделах меню добавлен явный пункт возврата в главное меню.

Командный режим для автоматизации:
```
python manage.py status
python manage.py run bot --mode background
python manage.py run bot --action status
python manage.py run bot --action stop
python manage.py service bot status --scope user
python manage.py smoke --url https://bot-test.justasite.cc/webapp
python manage.py governance checks --branch main
python manage.py governance checklist
python manage.py backup create
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

Опциональный мониторинг nginx в `monitor check`:
- в `config.py`:
  - `MONITOR_NGINX_ENABLED = True`
  - `MONITOR_NGINX_UNIT = "nginx.service"` (или ваш unit)
- переменные окружения с теми же именами работают как override, но не обязательны.

Ежедневный операционный сценарий:
```
# 1) Проверка состояния
python manage.py status
python manage.py monitor check

# 2) Backup (разово или по расписанию)
python manage.py backup create
python manage.py backup verify

# 3) При необходимости — рассылка
python manage.py broadcast --audience approved --changelog-latest --dry-run
python manage.py broadcast --audience approved --changelog-latest --confirm
```

Пример рассылки в командном режиме:
```
# Предпросмотр (без отправки)
python manage.py broadcast --audience approved --changelog-latest --dry-run

# Реальная отправка (требуется --confirm)
python manage.py broadcast --audience approved --changelog-latest --confirm
```

Скрипт `broadcast.py` сохранен для обратной совместимости и может использоваться напрямую.

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
python manage.py broadcast --audience approved --changelog-latest --dry-run
python manage.py broadcast --audience approved --changelog-latest --confirm
```

## Документация

- Подробное описание функций и ролей — в `DOCUMENTATION.md`.
- Короткий пользовательский changelog — в `CHANGELOG.md`.
- Архив реализованных RFC — в `docs/archive/`.
- Завершенный RFC операционной панели — `docs/rfc/OPERATIONS_CLI_PANEL_RFC.md`.

## Структура проекта

- `app/entrypoints/` — реальные точки входа приложений (`bot_main.py`, `webapp_main.py`, `notifications_main.py`).
- `app/config/settings.py` — чтение runtime-настроек и секретов.
- `app/db/` + `app/repositories/` — SQL-слой и фасады репозиториев.
- `app/use_cases/` — бизнес-сценарии (отсутствия, модерация, пересечения, экспорты).
- `app/ops/` — операционный CLI-слой (menu/status/service/smoke/broadcast/backup/alerts/monitor).
- `app/webapp/` — WebApp-слой:
  - `api.py` (HTTP handlers/factory),
  - `auth.py` (initData/auth),
  - `http.py` (security headers/rate-limit middleware),
  - `validation.py` (валидация query/path),
  - `service.py` (read-only ACL/данные),
  - `export.py` (XLSX).
- `handlers/` — Telegram-хендлеры по доменам (админ, группы, отсутствия, меню).
- `core.py`, `keyboards.py`, `texts.py`, `utils.py` — общий слой Telegram-бота.
- `database.py` — инициализация схемы SQLite.
- `tests/` — тесты.
- `manage.py`, `manage` — единая CLI-панель (командный + интерактивный режимы).
- `bot.py`, `webapp_api.py`, `webapp_readonly.py`, `webapp_export.py`, `settings.py`, `db_repo.py` — совместимые shim-модули.
- `config.py` — локальный fallback-конфиг (не хранится в git), `config_example.py` — пример.
- `deploy/env/telegram_bot.env.example` — шаблон production EnvironmentFile (секреты).
