"""Botni ishga tushiruvchi asosiy fayl."""
import asyncio
import logging
import shutil

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

import config
from handlers import routers
from middlewares import SubscriptionMiddleware
from services import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("main")


async def start_health_server() -> web.AppRunner:
    """Render Web Service port kutadi. UptimeRobot kabi servis shu manzilni ping qilishi mumkin."""
    async def ok(_):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    log.info("Health server: port %s", config.PORT)
    return runner


async def main() -> None:
    config.validate()

    shutil.rmtree(config.DOWNLOAD_DIR, ignore_errors=True)  # qolib ketgan vaqtinchalik fayllar
    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    await db.init()

    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg tizimda topilmadi! Dockerfile ishlating yoki imageio-ffmpeg zaxirasiga tayaning.")
    if not (config.SPOTIFY_CLIENT_ID and config.SPOTIFY_CLIENT_SECRET):
        log.warning("Spotify kalitlari yo'q: havola tahlili ishlamaydi, faqat to'g'ridan-to'g'ri qidiruv bo'ladi.")

    bot = Bot(
        token=config.BOT_TOKEN,
        session=AiohttpSession(timeout=300),  # katta audio yuklash uchun
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    sub_mw = SubscriptionMiddleware()
    dp.message.outer_middleware(sub_mw)
    dp.callback_query.outer_middleware(sub_mw)
    dp.inline_query.outer_middleware(sub_mw)

    for r in routers:
        dp.include_router(r)

    runner = await start_health_server()

    await bot.set_my_commands([
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="help", description="Yordam"),
    ])
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.set_my_commands(
                [BotCommand(command="start", description="Botni ishga tushirish"),
                 BotCommand(command="help", description="Yordam"),
                 BotCommand(command="stat", description="Statistika"),
                 BotCommand(command="broadcast", description="Hammaga xabar yuborish")],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:
            log.warning("Admin buyruqlarini o'rnatib bo'lmadi (%s): %s", admin_id, e)

    me = await bot.get_me()
    log.info("Bot ishga tushdi: @%s", me.username)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi")
