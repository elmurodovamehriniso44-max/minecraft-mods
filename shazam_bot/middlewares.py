import logging
from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from services import db, utils

logger = logging.getLogger(__name__)

SUB_TEXT = (
    "📢 <b>Botdan foydalanish uchun kanalimizga obuna bo'ling!</b>\n\n"
    "Obuna bo'lgach, «✅ Tekshirish» tugmasini bosing."
)


class UserTrackerMiddleware(BaseMiddleware):
    """Har bir foydalanuvchini bazaga yozib boradi (statistika va broadcast uchun)."""

    def __init__(self) -> None:
        self._seen: set[int] = set()

    async def __call__(self, handler: Callable, event: TelegramObject, data: dict[str, Any]):
        user = data.get("event_from_user")
        if user and not user.is_bot and user.id not in self._seen:
            try:
                await db.add_user(user.id, user.username, user.full_name)
                self._seen.add(user.id)
            except Exception:
                logger.exception("Foydalanuvchini saqlashda xatolik")
        return await handler(event, data)


class SubscriptionMiddleware(BaseMiddleware):
    """Kanalga a'zo bo'lmaganlarni to'xtatadi (message va callback uchun)."""

    async def __call__(self, handler: Callable, event: TelegramObject, data: dict[str, Any]):
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)
        if await utils.is_subscribed(data["bot"], user.id):
            return await handler(event, data)
        try:
            if isinstance(event, Message):
                await event.answer(SUB_TEXT, reply_markup=utils.subscribe_kb())
            elif isinstance(event, CallbackQuery):
                await event.answer("Avval kanalga obuna bo'ling!", show_alert=True)
                if event.message:
                    await event.message.answer(SUB_TEXT, reply_markup=utils.subscribe_kb())
        except Exception:
            logger.exception("Obuna xabarini yuborishda xatolik")
        return None
