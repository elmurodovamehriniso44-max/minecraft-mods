import asyncio
import logging
import os
import shutil

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat
from aiohttp import web

import config
from handlers import admin, inline, music, start
from middlewares import SubscriptionMiddleware, UserMiddleware
from services import downloader
from services.db import db

log = logging.getLogger("main")


async def start_health_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()
    return runner


async def setup_commands_and_checks(bot: Bot) -> None:
    user_cmds = [BotCommand(command="start", description="Botni ishga tushirish"),
                 BotCommand(command="help", description="Yordam")]
    admin_cmds = user_cmds + [
        BotCommand(command="admin", description="Admin panel"),
        BotCommand(command="stat", description="Statistika"),
        BotCommand(command="diag", description="Diagnostika"),
        BotCommand(command="broadcast", description="Xabar yuborish"),
    ]
    try:
        await bot.set_my_commands(user_cmds)
        for aid in config.ADMIN_IDS:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=aid))
    except Exception as e:
        log.warning("Komandalarni o'rnatib bo'lmadi: %s", e)

    problems = []
    if not shutil.which("ffmpeg"):
        problems.append("❌ ffmpeg topilmadi (audio yuklab bo'lmaydi)")
    if not downloader.JS_RUNTIMES:
        problems.append("⚠️ deno/node topilmadi (YouTube yuklashi ishlamasligi mumkin)")
    if problems:
        log.error("Muammolar: %s", problems)
        for aid in config.ADMIN_IDS:
            try:
                await bot.send_message(aid, "⚠️ Bot ishga tushdi, lekin:\n" + "\n".join(problems) + "\n\nBatafsil: /diag")
            except Exception:
                pass


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi (.env yoki environment variables)")

    await db.init()
    await db.get_channels()  # .env kanallarini birinchi marta bazaga ko'chiradi
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(UserMiddleware())
        observer.outer_middleware(SubscriptionMiddleware())
    dp.inline_query.outer_middleware(UserMiddleware())

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(inline.router)
    dp.include_router(music.router)  # eng oxirida: umumiy matn handleri

    await bot.delete_webhook(drop_pending_updates=True)
    await setup_commands_and_checks(bot)
    runner = await start_health_server()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
