import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config.settings import TOKEN
from database import init_db
from handlers import absences, admin, groups, menus


def _build_dispatcher(bot: Bot) -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())

    admin.set_bot(bot)
    groups.set_bot(bot)
    absences.set_bot(bot)

    # Keep menu fallback router last so specific handlers have priority.
    dispatcher.include_router(admin.router)
    dispatcher.include_router(groups.router)
    dispatcher.include_router(absences.router)
    dispatcher.include_router(menus.router)
    return dispatcher


async def main() -> None:
    logging.basicConfig(level=logging.DEBUG)
    init_db()

    bot = Bot(token=TOKEN)
    dispatcher = _build_dispatcher(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен!")
    await dispatcher.start_polling(bot)

