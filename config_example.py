# Пример конфига Telegram-бота
# Скопируйте этот файл как config.py и укажите токен

TOKEN = "PUT_YOUR_TOKEN_HERE"
DB_NAME = "bot_database.db"

# Публичный HTTPS-URL для Telegram WebApp.
# Если пусто — кнопка "Пересечения (WebApp)" в меню не показывается.
WEBAPP_URL = ""

# Dev fallback для WebApp API (доступ по X-Telegram-User-Id без initData).
# В production должно быть False.
WEBAPP_ALLOW_DEV_FALLBACK = False

# Режим совместимости каналов initData (query/cookie/referer).
# Для production рекомендуется False.
WEBAPP_ALLOW_INITDATA_COMPAT = False

# Параметры запуска WebApp API.
WEBAPP_HOST = "127.0.0.1"
WEBAPP_PORT = 8080

# Rate limit для /webapp/v1/* (по IP).
WEBAPP_RATE_LIMIT_MAX_REQUESTS = 120
WEBAPP_RATE_LIMIT_WINDOW_SEC = 60
