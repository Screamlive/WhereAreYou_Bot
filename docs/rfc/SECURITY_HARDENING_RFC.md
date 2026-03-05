# RFC: Усиление безопасности бота и WebApp

Дата: 2026-03-05  
Статус: Draft (к поэтапной реализации)

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
- обходные механики desktop-совместимости (query/cookie/localStorage для `initData`) расширяют поверхность утечки;
- отсутствие rate limiting на `/webapp/v1/*`;
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

Базовые тесты есть (ACL/auth), но не хватает:
- тестов на санитизацию логов;
- тестов на transport-политику (prod без fallback);
- тестов на заголовки безопасности;
- интеграционных тестов с reverse proxy / tunnel профилями.

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

## 6) План внедрения (итерации)

### Итерация S1 — Быстрые исправления (низкий риск)

- Убрать потенциально чувствительные debug-логи.
- Документально зафиксировать prod-переменные и запрет fallback.
- Добавить checklist проверки открытых портов после деплоя.

Критерии приемки:
- Нет утечек `initData`/query в логах.
- Документация содержит явный prod baseline.

### Итерация S2 — Proxy hardening

- Добавить security headers в Nginx-шаблон.
- Добавить раздел для Cloudflare Tunnel hardening (Zero Trust/IP rules по возможности).
- Ограничить методы/роуты, где это применимо.

Критерии приемки:
- Проверка через `curl -I` показывает обязательные headers.
- Сценарии Nginx/Tunnel описаны единообразно.

### Итерация S3 — Auth hardening

- Минимизировать каналы передачи `initData`.
- Убрать persistent storage `initData` в production режиме.
- Добавить rate limit на `/webapp/v1/*`.

Критерии приемки:
- Нагрузочный smoke не приводит к деградации.
- Без `initData` данные недоступны стабильно во всех роутингах.

### Итерация S4 — Security tests & release gate

- Добавить тесты на:
  - отсутствие dev fallback в prod-конфигурации,
  - отсутствие секретов в логах,
  - headers безопасности,
  - ACL regression.
- Ввести release gate: деплой без прохождения security-набора запрещен.

Критерии приемки:
- Security test suite green.
- Release checklist формализован.

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
- [ ] Нет debug-логов с `Referer`/query/initData.
- [ ] `webapp_api.py` не торчит наружу на `8080`.
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
