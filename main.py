import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import db
import handlers_admin
import handlers_user
from config import config
from keyboards import main_menu

WEBHOOK_PATH = "/webhook"


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def on_startup(bot: Bot):
    if config.webhook_base:
        await bot.set_webhook(
            url=config.webhook_base + WEBHOOK_PATH,
            secret_token=config.webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        logging.info("Webhook o'rnatildi: %s", config.webhook_base + WEBHOOK_PATH)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(Command("cancel"))
    async def cancel(m: Message, state: FSMContext):
        await state.clear()
        await m.answer("❌ Bekor qilindi.", reply_markup=main_menu())

    dp.include_routers(handlers_admin.router, handlers_user.router)
    dp.startup.register(on_startup)
    return dp


async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    if config.webhook_base:
        # Render / hosting: webhook + health-check
        app = web.Application()
        app.router.add_get("/", health)
        app.router.add_get("/health", health)
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.webhook_secret).register(
            app, path=WEBHOOK_PATH
        )
        setup_application(app, dp, bot=bot)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", config.port).start()
        logging.info("Server %s portda ishga tushdi", config.port)
        await asyncio.Event().wait()
    else:
        # Mahalliy sinov: polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
