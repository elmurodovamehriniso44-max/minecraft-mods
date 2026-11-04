import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

import config
from services.db import db
from services.subscription import get_unsubscribed, subscribe_keyboard

log = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if u and not u.is_bot:
            try:
                await db.upsert_user(u.id, u.username, u.full_name)
            except Exception:
                log.exception("Foydalanuvchini saqlashda xato")
        return await handler(event, data)


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user or user.id in config.ADMIN_IDS or not await db.get_channels():
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)
        if isinstance(event, Message) and event.chat.type != "private":
            return await handler(event, data)

        bot = data["bot"]
        missing = await get_unsubscribed(bot, user.id)
        if not missing:
            return await handler(event, data)

        text = "🔒 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, so'ng «Tekshirish» tugmasini bosing:"
        if isinstance(event, CallbackQuery):
            await event.answer("Avval kanallarga obuna bo'ling!", show_alert=True)
        await bot.send_message(user.id, text, reply_markup=subscribe_keyboard(missing))
        return None
