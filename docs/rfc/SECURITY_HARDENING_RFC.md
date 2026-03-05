# RFC: Усиление безопасности бота и WebApp

Дата: 2026-03-05  
Статус: In Progress

## Статус выполнения (на 2026-03-05)

- [x] S1: санитизация логов (`Referer`/query/initData не логируются в сыром виде).
- [x] S1: backend bind по умолчанию переведен на `WEBAPP_HOST=127.0.0.1`.
- [x] S1: документация дополнена prod-baseline и ручными проверками.
- [x] S2: security headers добавлены в `webapp_api.py` и в Nginx-шаблон.
- [x] S2: ограничения HTTP-методов для WebApp добавлены в Nginx-шаблон.
- [x] S2: добавлен unit-тест на обязательные security headers.
- [x] S2: финальная ручная проверка headers на реальном edge (Nginx/Tunnel).
- [x] S3: auth hardening реализован (флаг compat-каналов, удален persistent initData, rate limit).
- [x] S3: добавлены unit-тесты для strict-режима compat и rate limit.
- [x] S3: финальный ручной smoke rate limit на edge выполнен (`401`/`429` подтверждены).
- [ ] S4: полный security gate для релиза.

## 1) Цель

Сформировать и реализовать целевую модель безопасности для:
- Telegram-бота (chat-интерфейс);
- WebApp (read-only пересечения);
- инфраструктуры (сервер, reverse proxy/tunnel, systemd-сервисы).

Результат: предсказуемый и проверяемый security baseline для production.

## 2) Ограничения и ключевой факт

Telegram WebApp по модели платформы открывается с публичного HTTPS URL.  
Полностью закрыть сам HTML от прямого открытия извне нельзя без потери штатного сценария.

Следовательно, защита строится так:
- можно открывать страницу (`/webapp`);
- нельзя получать данные (`/webapp/v1/*`) без валидного Telegram `initData`.

## 3) Текущая защита (что уже есть)

1. Проверка подписи `initData` на backend (`webapp_api.py`).
2. Контроль срока `auth_date` (`initData` устаревает).
3. ACL по ролям и scope (global/group/superadmins) в `webapp_readonly.py`.
4. Отклонение запросов без контекста: `401/403`.
5. Dev fallback отключаемый (`WEBAPP_ALLOW_DEV_FALLBACK=0` для prod).
6. Набор unit-тестов на ACL и auth:
   - `tests/test_webapp_api.py`
   - `tests/test_webapp_readonly.py`
   - `tests/test_security_handlers.py`

## 4) Ответы на ключевые вопросы

### 4.1 Можно ли ограничить доступ к WebApp только из Telegram?

Полностью и надежно — нет.  
Telegram не дает “железного” transport-level маркера, который невозможно подделать извне.

### 4.2 Можно ли отдавать 403?

Да, и уже делается для data endpoints при отсутствии/невалидности `initData` и нарушении ACL.  
Для `/webapp` (HTML) рекомендуется не 403, а безопасный “пустой shell”, иначе ломается UX открытия.

### 4.3 Есть ли потенциальные уязвимости?

Да, текущие риски:
- возможная утечка чувствительных параметров через чрезмерно подробный debug-лог;
- compat-каналы `initData` (query/cookie/referer) расширяют поверхность утечки, если не отключены;
- двойной источник конфигурации повышает риск дрейфа настроек между средами;
- отсутствие обязательного набора security headers;
- риск внешнего доступа к backend-порту при неправильном bind/firewall.

### 4.4 Раз IP сервера виден, что делать?

Нужен стандартный hardening:
- firewall (allowlist нужных портов);
- закрыть внешний доступ к `8080` (только localhost/tunnel);
- SSH только по ключам, отключить password auth;
- fail2ban/аналог;
- регулярные обновления ОС и пакетов;
- non-root сервисы;
- резервные копии БД и проверка восстановления.

### 4.5 Как у нас с security-тестами?

Базовые тесты есть (ACL/auth/sanitization/headers/rate limit), но не хватает:
- интеграционных тестов с reverse proxy / tunnel профилями;
- автоматизированного release gate в CI.

## 5) Целевой security baseline (production)

## 5.1 Backend/Auth

1. `WEBAPP_ALLOW_DEV_FALLBACK=0` в production жестко.
2. Принимать `initData` только в разрешенных каналах; временные совместимости держать под флагом.
3. Исключить хранение `initData` в localStorage в production режиме.
4. Запретить логирование `initData`, query с токенами и сырых `Referer`.
5. Единый формат ошибок для auth (без утечки деталей в клиент).

## 5.2 HTTP/Proxy

Для Nginx (или edge-слоя) включить:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin` (или строже)
- `Permissions-Policy` (минимальный набор)
- умеренный `Content-Security-Policy` для WebApp статики
- `Strict-Transport-Security` (после стабилизации TLS)

## 5.3 Network

1. `webapp_api.py` слушает `127.0.0.1` (или firewall deny внешнего `8080`).
2. Открыты только необходимые порты:
   - Nginx-профиль: `22`, `80`, `443`;
   - Tunnel-профиль: `22` (+ исходящий трафик cloudflared), без входящего `80/443`.
3. Явная проверка после деплоя: порт `8080` недоступен извне.

## 5.4 Runtime/Operations

1. Сервисы от непривилегированного пользователя.
2. Лог-ротация.
3. Мониторинг ошибок `401/403/5xx` и аномалий запросов.
4. Обязательный backup + restore drill.

## 5.5 Configuration & Secrets

1. Единая модель конфигурации:
   - в коде единая точка чтения настроек (`settings`/`config`);
   - в production используется один основной канал поставки значений.
2. Секреты (`TOKEN` и т.п.) не хранятся в git и `config.py`:
   - только через `systemd EnvironmentFile` (например, `/etc/telegram_bot/telegram_bot.env`, права `600`)
     или внешний secret manager.
3. Переменные окружения используются как override осознанно и документированно.
4. Fail-fast: при отсутствии обязательных параметров production-сервис не стартует.
5. `.env` допустим только для локальной разработки, не для production.

## 6) План внедрения (итерации)

### Итерация S1 — Быстрые исправления (низкий риск)

- Убрать потенциально чувствительные debug-логи.
- Документально зафиксировать prod-переменные и запрет fallback.
- Добавить checklist проверки открытых портов после деплоя.

Критерии приемки:
- Нет утечек `initData`/query в логах.
- Документация содержит явный prod baseline.

Текущий статус: выполнено.

### Итерация S2 — Proxy hardening

- Добавить security headers в Nginx-шаблон.
- Добавить раздел для Cloudflare Tunnel hardening (Zero Trust/IP rules по возможности).
- Ограничить методы/роуты, где это применимо.

Критерии приемки:
- Проверка через `curl -I` показывает обязательные headers.
- Сценарии Nginx/Tunnel описаны единообразно.

Текущий статус: реализовано в коде и шаблонах, требуется финальная проверка на боевом edge.

### Итерация S3 — Auth hardening

- Минимизировать каналы передачи `initData`.
- Убрать persistent storage `initData` в production режиме.
- Добавить rate limit на `/webapp/v1/*`.

Критерии приемки:
- Нагрузочный smoke не приводит к деградации.
- Без `initData` данные недоступны стабильно во всех роутингах.

Текущий статус: реализовано в коде и unit-тестах, требуется финальный edge smoke (429).

### Итерация S4 — Security tests & release gate

- Добавить тесты на:
  - отсутствие dev fallback в prod-конфигурации,
  - отсутствие секретов в логах,
  - headers безопасности,
  - ACL regression.
- Ввести release gate: деплой без прохождения security-набора запрещен.
- Зафиксировать и проверить policy конфигурации/секретов (single source of truth + fail-fast).

Критерии приемки:
- Security test suite green.
- Release checklist формализован.

Текущий статус: частично (база тестов расширена), полный release gate не внедрен.

## 7) Тестовая стратегия безопасности

1. Unit:
- проверка auth веток (`initData` valid/invalid/missing/expired);
- ACL по ролям и scope.

2. Integration:
- `curl` сценарии через Nginx/Tunnel;
- проверка заголовков безопасности;
- проверка кода ответа на запросы без контекста.

3. Ops:
- проверка открытых портов (`ss`/`nmap` внутри CI smoke/руками);
- проверка, что backend API не доступен по внешнему IP на `8080`.

## 8) Чеклист релиза (security)

- [ ] `WEBAPP_ALLOW_DEV_FALLBACK=0` в prod.
- [ ] `WEBAPP_ALLOW_INITDATA_COMPAT=0` в prod.
- [ ] `TOKEN` и прочие секреты не хранятся в репозитории.
- [ ] Production запускается через `EnvironmentFile` с ограниченными правами доступа (`600`).
- [ ] Нет debug-логов с `Referer`/query/initData.
- [ ] `webapp_api.py` не торчит наружу на `8080`.
- [ ] Настроен и проверен rate limit (`429` при burst на `/webapp/v1/*`).
- [ ] Настроены backup и проверено восстановление.
- [ ] Пройдены security unit/integration тесты.
- [ ] Проверены SSH/firewall/fail2ban/обновления.

## 9) Out of scope

- Полноценный SIEM/SOC.
- SSO/внешний IAM.
- Полноценный WAF enterprise-класса.

## 10) Вывод

Текущая система уже имеет правильный базис (initData + ACL), но для
production-grade уровня нужен формализованный hardening по сети, логам,
headers и release-gate на security тестах.
