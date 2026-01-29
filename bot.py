import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import TOKEN
from database import init_db
from handlers import admin, groups, absences, menus

logging.basicConfig(level=logging.DEBUG)

init_db()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin.set_bot(bot)
groups.set_bot(bot)
absences.set_bot(bot)

# Важно: меню с fallback подключаем последним
# чтобы остальные хендлеры имели приоритет

dp.include_router(admin.router)
dp.include_router(groups.router)
dp.include_router(absences.router)
dp.include_router(menus.router)


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
