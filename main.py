import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

import config
from handlers import admin, inline, music, start
from middlewares import SubscriptionMiddleware, UserMiddleware
from services.db import db


async def start_health_server() -> web.AppRunner:
    """Render Web Service port kutadi; shu uchun kichik health-check server."""
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()
    return runner


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi (.env yoki environment variables)")

    await db.init()
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Tartib muhim: avval foydalanuvchini yozamiz, keyin obunani tekshiramiz
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(UserMiddleware())
        observer.outer_middleware(SubscriptionMiddleware())
    dp.inline_query.outer_middleware(UserMiddleware())

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(inline.router)
    dp.include_router(music.router)  # eng oxirida: umumiy matn handleri

    await bot.delete_webhook(drop_pending_updates=True)
    runner = await start_health_server()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
