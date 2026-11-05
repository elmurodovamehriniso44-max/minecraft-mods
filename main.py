import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ErrorEvent

import config
from handlers import admin, inline, music, start
from middlewares import SubscriptionMiddleware, UserTrackerMiddleware
from services import db, utils

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("main")

POLITE = "😔 Kutilmagan xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring."


async def health(_: web.Request) -> web.Response:
    return web.Response(text="OK")


async def start_health_server() -> web.AppRunner:
    """Render Web Service port ochiq bo'lishini talab qiladi (+ UptimeRobot ping uchun)."""
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    logger.info("Health server :%s portda ishga tushdi", config.PORT)
    return runner


async def main() -> None:
    await db.init()
    utils.cleanup_workdir()
    if not utils.find_ffmpeg():
        logger.error("ffmpeg topilmadi! Render'da Dockerfile ishlating.")
    logger.info("cookies.txt: %s | player_client: %s", config.COOKIES_FILE or "yo'q", config.YT_PLAYER_CLIENTS)

    runner = await start_health_server()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        if isinstance(event.exception, TelegramForbiddenError):
            return True
        logger.error("Handlerda xatolik", exc_info=event.exception)
        try:
            upd = event.update
            if upd.message:
                await upd.message.answer(POLITE)
            elif upd.callback_query:
                await upd.callback_query.answer(POLITE, show_alert=True)
        except Exception:
            pass
        return True

    tracker, sub = UserTrackerMiddleware(), SubscriptionMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(tracker)
        observer.outer_middleware(sub)

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(music.router)  # umumiy matn handler — start/admin'dan keyin
    dp.include_router(inline.router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        me = await bot.me()
        logger.info("Bot ishga tushdi: @%s", me.username)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await runner.cleanup()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi")
