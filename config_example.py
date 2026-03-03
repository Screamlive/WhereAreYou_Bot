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
