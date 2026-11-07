"""Minecraft Bedrock Addons Telegram boti — ishga tushirish fayli."""
import asyncio
import logging
import os
from aiohttp import web


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()
    return runner

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

import config
from database import db
from handlers import admin, catalog, common, fallback, mod_requests
from utils import texts as T
from utils.middlewares import ThrottleMiddleware, UserTrackingMiddleware

log = logging.getLogger("bot")


async def on_error(event: ErrorEvent) -> bool:
    log.error("Handlerda xatolik: %s", event.exception, exc_info=event.exception)
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer(T.ERROR_GENERIC, show_alert=True)
        elif update.message:
            await update.message.answer(T.ERROR_GENERIC)
    except TelegramAPIError:
        pass
    return True


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    if not config.ADMIN_IDS:
        log.warning("ADMIN_IDS bo'sh! Admin panel hech kimga ochiq bo'lmaydi.")

    await db.init_db()
    health = await start_health_server()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    throttle = ThrottleMiddleware()
    tracking = UserTrackingMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)
        observer.outer_middleware(tracking)

    dp.errors.register(on_error)

    # Tartib muhim: common (buyruqlar) birinchi, fallback oxirgi
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(catalog.router)
    dp.include_router(mod_requests.router)
    dp.include_router(fallback.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="menu", description="Bosh menyu"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="cancel", description="Amalni bekor qilish"),
    ])

    try:
        me = await bot.get_me()
        log.info("Bot ishga tushdi: @%s", me.username)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close_db()
        await bot.session.close()
        await health.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi.")
