# RFC: Операционная CLI-панель управления компонентами

Дата: 2026-03-05  
Статус: Completed

## Статус выполнения (на 2026-03-06)

- [x] C1: добавлены `manage.py` и launcher `./manage`, реализованы команды `status`, `run`.
- [x] C2: добавлены `service` wrappers и `smoke`.
- [x] C3: добавлен безопасный `broadcast` wrapper (`--confirm` для реальной отправки).
- [x] C4: добавлены `backup create/list/verify/restore/prune/usage`.
- [x] Добавлен интерактивный режим `menu` с wizard-потоками для ключевых операций.
- [x] Улучшен UX меню: очистка экрана между шагами и цветовые статусы health/backup.
- [x] Локальные компоненты (без systemd): запуск в фоне, статус и остановка из CLI/menu.
- [x] Добавлены базовые unit-тесты CLI (`tests/test_ops_cli.py`).
- [x] C5: добавлены governance-команды (`governance checks`, `governance checklist`) в командном режиме CLI.
- [x] C6: выполнена ревизия root shim-модулей, решения зафиксированы (оставить/удалить).
- [x] C7: добавлен планировщик backup (systemd timer через CLI/menu) + глубина хранения.
- [x] C8: добавлен мониторинг свободного места и ранние предупреждения (warning/critical).
- [x] C9: добавлены тех-уведомления (контакты, monitor check, anti-spam state, monitor timer, событийные `OnFailure` alerts).
- [x] Операционный scope по умолчанию для `bot`/`webapp` переведен на `user` (systemd user services).

## 1) Проблема

Проект включает несколько компонентов:
- `bot.py` (основной Telegram-бот);
- `webapp_api.py` (backend для WebApp);
- `notifications.py` (ежедневные сводки);
- `broadcast.py` (сервисные рассылки);
- systemd/user timers + окружение.

Сейчас операции выполняются набором разрозненных команд. Это повышает риск ошибок
при запуске, деплое и диагностике.

## 2) Цель

Сделать единый операционный CLI-слой для:
- запуска/остановки/статуса сервисов;
- health/smoke проверок;
- безопасной рассылки;
- стандартных release/deploy операций.

CLI не заменяет systemd, а даёт единый интерфейс поверх текущих механизмов.

## 3) Non-goals

- не строим GUI/веб-панель админки;
- не переносим бизнес-логику бота в CLI;
- не заменяем CI/CD pipeline.

## 4) Пользователи CLI

1. Владелец продукта/админ сервера (основной пользователь).
2. Техподдержка (стандартные действия без глубокого знания systemd).

## 5) Целевой UX

Единая точка входа:
```
python manage.py <команда> [опции]
```

или эквивалентный launcher:
```
./manage <команда>
```

Принципы:
- безопасные дефолты;
- dry-run там, где есть риск массовых действий;
- понятные коды завершения и короткий, читаемый вывод.

### 5.1 Режимы работы CLI

1. Командный режим (для автоматизации/CI):
   - `python manage.py status`
   - `python manage.py service bot restart`
2. Интерактивный режим (для ручной эксплуатации):
   - `python manage.py menu`
   - или запуск без аргументов как алиас на `menu`.

Интерактивный режим — это текстовое меню в терминале:
- `1) Статус компонентов`
- `2) Разовый запуск компонента`
- `3) Управление systemd-сервисами`
- `4) Рассылка (wizard: источник, аудитория, предпросмотр, подтверждение)`
- `5) Проверка smoke`
- `6) Backup`
- `7) Мониторинг и тех-уведомления`
- `8) Выход`

Важно: интерактивный режим не заменяет командный, а использует те же backend-команды.

## 6) Предлагаемая структура команд (MVP)

## 6.1 `status`

Проверяет:
- процессы `bot.py`, `webapp_api.py`, `cloudflared` (если используется);
- состояние timer/service уведомлений;
- выбранный профиль (`test`/`prod`) и базовые env-параметры.

Пример:
```
python manage.py status
```

## 6.2 `run`

Локальный запуск компонентов:
- `run bot`
- `run webapp`
- `run notify-once`

Поддерживает режимы:
- `--mode foreground` (блокирует текущий терминал);
- `--mode background` (запуск в фоне, лог в `.runtime/logs/*`).

Поддерживает действия для фоновых процессов:
- `--action status`
- `--action stop [--force]`

Примеры:
```
python manage.py run bot --mode background
python manage.py run bot --action status
python manage.py run bot --action stop
python manage.py run notify-once --mode foreground
```

## 6.3 `service`

Обертка над systemd/systemd-user:
- `service bot restart`
- `service webapp restart`
- `service notify-timer status`

С явным указанием типа (`system`/`user`) и проверкой прав.

## 6.4 `broadcast`

Безопасный wrapper над `broadcast.py`:
- по умолчанию `--dry-run`;
- подтверждение перед реальной рассылкой;
- поддержка `--changelog-latest`.

Пример:
```
python manage.py broadcast approved --changelog-latest --dry-run
python manage.py broadcast approved --changelog-latest --confirm
```

## 6.5 `smoke`

Быстрые проверки перед релизом:
- API `/webapp/v1/me` (dev/test контур);
- доступность WebApp URL;
- базовый статус сервисов.

## 6.6 `backup`

Операции с БД:
- `backup create`
- `backup list`
- `backup verify`
- `backup restore --path <file>`
- `backup prune --retain N`
- `backup usage`

Восстановление выполняется только с явным указанием backup-файла и подтверждением оператора.

## 6.7 `governance`

Операционные проверки репозитория/релиза:
- `governance checks` — проверка, что обязательные release-gates включены;
- `governance checklist` — печать чеклиста перед релизом.

Минимум для MVP:
- контроль, что для `main` включен PR-only merge;
- контроль обязательного check `security-gate` в branch protection.

## 6.8 `alerts`

Управление техконтактами и тестовая отправка:
- `alerts contacts list`
- `alerts contacts add --id <telegram_id>`
- `alerts contacts remove --id <telegram_id>`
- `alerts test --message "..."`

## 6.9 `monitor`

Мониторинг инцидентов и авто-уведомления:
- `monitor check` — локальный check без отправки;
- `monitor check --notify` — check + уведомление техконтактов;
- `monitor schedule-enable --interval N` — включить timer monitor-job;
- `monitor schedule-disable|schedule-status|schedule-run` — управление monitor scheduler.
- `monitor events-enable [--units CSV]` — включить событийные `OnFailure` алерты для service-unit;
- `monitor events-disable|events-status` — управление/проверка событийных алертов.

## 7) Архитектура CLI

## 7.1 Технология

Рекомендуется `argparse` (без лишних зависимостей) либо `Typer` (лучший UX).

Рекомендация для проекта: начать с `argparse` (минимум риска/зависимостей).

## 7.2 Слои

1. `manage.py` — парсинг CLI и маршрутизация.
2. `app/ops/` модуль:
   - `app/ops/cli.py`
   - `app/ops/menu.py`
   - `app/ops/status_ops.py`
   - `app/ops/service_ops.py`
   - `app/ops/smoke_ops.py`
   - `app/ops/broadcast_ops.py`
   - `app/ops/backup_ops.py`
   - `app/ops/backup_planner_ops.py`
   - `app/ops/alerts_ops.py`
   - `app/ops/monitor_ops.py`
   - `app/ops/systemd_units.py`
3. Конфигурация профилей:
   - `ops/profiles/test.env`
   - `ops/profiles/prod.env` (без секретов в git, только шаблоны).

## 7.3 Политика безопасности для CLI

- команды массовой рассылки/restore требуют `--confirm`;
- вывод не должен печатать токены/секреты;
- destructive-операции имеют дополнительное подтверждение;
- все команды пишут операционный лог (в файл/таблицу логов).

## 8) Совместимость с текущей инфраструктурой

CLI должен поддерживать 2 сценария публикации WebApp:
- Nginx + прямой DNS;
- Cloudflare Tunnel.

CLI не обязан управлять всей сетевой инфраструктурой, но должен уметь
валидировать состояние (процесс, порт, endpoint, URL).

## 9) План внедрения

### Итерация C1 — Каркас CLI

- добавить `manage.py` и базовые команды `status`, `run`.
- реализовать нормализованный вывод и коды ошибок.

Критерии:
- можно одной командой понять состояние ключевых компонентов.

### Итерация C2 — Service и smoke

- добавить `service` wrappers;
- добавить `smoke` для test/prod профилей.

Критерии:
- перед релизом есть однозначная команда preflight-проверки.

### Итерация C3 — Broadcast wrapper

- добавить безопасную обертку для рассылок с confirm-flow;
- по умолчанию dry-run.

Критерии:
- невозможно случайно отправить массовую рассылку без явного подтверждения.

### Итерация C4 — Backup

- добавить backup/create/list/verify;
- документировать restore-процедуру.

Критерии:
- есть повторяемая процедура backup перед релизом.

### Итерация C5 — Governance и release-gates

- добавить `governance` команды;
- перенести операционный хвост из Security RFC:
  - branch protection `main` с check `security-gate`.

Критерии:
- есть явная проверка перед релизом, что ветка защищена по agreed policy.

Текущий статус: реализовано в CLI; фактическая настройка branch protection выполняется на GitHub стороне и проверяется командой `governance checks`.

### Итерация C6 — Завершение shim-миграции

- перенести хвост из RFC по структуре проекта:
  - ревизия root shim-модулей (`bot.py`, `webapp_api.py`, `settings.py`, `db_repo.py` и др.);
  - поэтапное удаление shim-модулей, которые больше не нужны.

Критерии:
- для каждого shim есть решение: оставить (с причиной) или удалить (с планом/датой).

Текущий статус: выполнено.  
Матрица решений:
- `bot.py` — оставить как thin-wrapper (стабильная команда `python bot.py`).
- `webapp_api.py` — оставить как thin-wrapper + compat aliases для тестов/импортов.
- `settings.py` — оставить как shim на `app.config.settings` (backward compatibility).
- `db_repo.py` — оставить как модуль-алиас на `app.db.db_repo` (поддержка legacy import и тестов).
- `notifications.py` / `broadcast.py` — оставить root-entrypoints для операционных сценариев.

### Итерация C7 — Backup planner

- добавить в CLI генерацию/управление systemd timer для backup-задач;
- задавать расписание и глубину хранения (`retain N`) через интерфейс CLI/menu.

Критерии:
- backup запускается по расписанию;
- после запуска автоматически применяется политика хранения.

Текущий статус: выполнено.
- команды CLI: `backup schedule-enable/schedule-disable/schedule-status/schedule-run`;
- в scheduler добавлены `create -> verify -> prune --retain N`;
- в интерактивном меню (`Backup`) добавлены те же операции.

### Итерация C8 — Disk guardrails

- добавить проверки свободного места перед backup/restore;
- добавить предупреждения при достижении порога (warning/critical).

Критерии:
- backup не стартует при критической нехватке места;
- оператор получает понятное предупреждение.

Текущий статус: выполнено.
- реализован `disk_guardrail_status()` (ok/warning/critical);
- `backup create/restore` останавливаются в `critical`;
- `status` и `backup usage` показывают guardrail-статус.

### Итерация C9 — Технические уведомления

- завести список техадминов (service contacts);
- добавить уведомления о:
  - падении компонентов,
  - ошибках backup/verify,
  - предупреждениях по свободному месту.

Критерии:
- при инцидентах уведомление уходит автоматически;
- есть настройка каналов и уровня критичности.

Текущий статус: выполнено.
- добавлен реестр техконтактов (`alerts contacts list/add/remove`);
- добавлена отправка тестового сообщения (`alerts test`);
- добавлен `monitor check [--notify]` с проверками:
  - bot/webapp down,
  - notify timer state,
  - disk warning/critical,
  - failed unit для backup/monitor jobs;
- добавлен anti-spam state для уведомлений (повторно не шлёт неизменившийся инцидент);
- добавлен monitor scheduler (`monitor schedule-enable/schedule-disable/schedule-status/schedule-run`).
- добавлен событийный режим: `OnFailure` drop-ins + template unit через `monitor events-enable/...`.

## 10) Тестирование CLI

1. Unit:
- парсинг аргументов;
- маршрутизация команд;
- обработка ошибок.

2. Integration:
- smoke на тестовом окружении;
- проверка взаимодействия с systemd (mock + реальный стенд).

3. Security:
- тесты, что секреты не попадают в stdout/log;
- тесты confirm-flow для опасных операций.

## 11) Риски

- рост сложности поддержки при слишком широком scope;
- дублирование логики systemd-команд;
- риск “скрытой магии” в командах деплоя.

Митигирование:
- минимальный MVP;
- явные и прозрачные действия;
- хорошая документация команд.

## 12) Критерии приемки MVP

- [x] Есть единый `manage.py`.
- [x] Команда `status` показывает состояние ключевых компонентов.
- [x] Команда `smoke` проверяет базовую работоспособность.
- [x] Массовая рассылка через CLI требует подтверждение.
- [x] Документация содержит сценарии ежедневного использования CLI.
- [x] Доступен интерактивный режим `menu` с базовыми операциями.
- [x] Хвосты из закрытых RFC (security/structure) перенесены и зафиксированы в плане.

## 13) Вывод

Операционная CLI-панель целесообразна. Она снизит количество ручных ошибок и
ускорит релизные процедуры, сохраняя текущую архитектуру (systemd + скрипты).
