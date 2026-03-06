# Security Policy

## Reporting a Vulnerability

Сообщайте о проблемах безопасности через GitHub Security Advisories как private report.

Если Security Advisories недоступны, используйте приватный канал связи с maintainers. Публичные issue для уязвимостей открывать не нужно.

## Current Security Baseline

В проекте уже есть следующие меры защиты:

- `TOKEN` не должен храниться в git и читается только из окружения (`EnvironmentFile`/export).
- `config.py` gitignored и используется как локальный runtime module.
- WebApp API проверяет Telegram `initData` и без валидного auth context отвечает `401/403`.
- Dev fallback по `X-Telegram-User-Id` отключаемый и не должен использоваться в production.
- Для `/webapp/v1/*` включен rate limit по IP.
- WebApp backend выставляет security headers и CSP.
- Frontend не сохраняет `initData` в `localStorage` и не кладет его в cookie/query string API-запросов.
- В репозитории есть `security-gate` workflow и локальный `scripts/security_gate.sh`.

## Production Expectations

Перед production-деплоем ожидается минимум:

- `config.py` существует, но не закоммичен.
- `TOKEN` хранится только в `/etc/telegram_bot/telegram_bot.env` (или временно через `export TOKEN=...` для разового запуска).
- `WEBAPP_ALLOW_DEV_FALLBACK=0`.
- `WEBAPP_ALLOW_INITDATA_COMPAT=0`.
- WebApp публикуется только через HTTPS.
- backend WebApp слушает локальный интерфейс, а не внешний `0.0.0.0`.
- внешний доступ к `:8080` закрыт proxy/firewall политикой.
- перед релизом запускается `./scripts/security_gate.sh`.

## Release Gate

`security-gate` сейчас делает три вещи:

- запускает focused security tests для WebApp и security-sensitive handlers;
- прогоняет полный `unittest discover -s tests`;
- выполняет статические проверки против опасного логирования и хранения `initData`.

CI workflow находится в `.github/workflows/security-gate.yml` и запускается на `push` и `pull_request` для `main`.

## Operational Notes

Есть текущие архитектурные ограничения, которые важно учитывать при hardening:

- проект еще не полностью избавился от прямых импортов `config`, поэтому `config.py` остается для несекретных параметров;
- настройка `DB_NAME` пока не централизована полностью, поэтому при переносе SQLite-файла нужно отдельно проверять runtime и backup-путь.

Это не считается приемлемой «окончательной» архитектурой, но это текущая реальность репозитория на момент обновления документации.

## Response Time

Цель по первичному подтверждению получения отчета: до 72 часов.
