"""Majburiy obuna (sub-check) middleware'i."""
import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQuery, InlineQueryResultsButton, Message, TelegramObject,
)

import config
from services import db

log = logging.getLogger(__name__)

_OK_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER}
_ok_cache: dict[int, float] = {}  # faqat obuna bo'lganlar, 2 daqiqa saqlanadi
_CACHE_TTL = 120


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    now = time.monotonic()
    if _ok_cache.get(user_id, 0) > now:
        return True
    try:
        member = await bot.get_chat_member(config.REQUIRED_CHANNEL, user_id)
    except TelegramAPIError as e:
        # Bot kanalda admin emas yoki kanal noto'g'ri -> foydalanuvchilarni qulflab qo'ymaymiz.
        log.error("Obuna tekshiruvi xatosi (bot kanalda adminmi?): %s", e)
        return True
    ok = member.status in _OK_STATUSES or (
        member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False)
    )
    if ok:
        _ok_cache[user_id] = now + _CACHE_TTL
    return ok


def _sub_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if config.CHANNEL_LINK:
        rows.append([InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=config.CHANNEL_LINK)])
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


SUB_TEXT = "🔒 Botdan foydalanish uchun avval kanalimizga obuna bo'ling, so'ng «✅ Tekshirish» tugmasini bosing."


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)

        await db.upsert_user(user.id, user.username, user.full_name)

        if not config.REQUIRED_CHANNEL or user.id in config.ADMIN_IDS:
            return await handler(event, data)

        bot: Bot = data["bot"]
        if await is_subscribed(bot, user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(SUB_TEXT, reply_markup=_sub_keyboard())
        elif isinstance(event, CallbackQuery):
            if event.data == "check_sub":
                await event.answer("❌ Siz hali obuna bo'lmagansiz!", show_alert=True)
            else:
                await event.answer("🔒 Avval kanalga obuna bo'ling.", show_alert=True)
                if event.message:
                    await event.message.answer(SUB_TEXT, reply_markup=_sub_keyboard())
        elif isinstance(event, InlineQuery):
            await event.answer(
                [], cache_time=1, is_personal=True,
                button=InlineQueryResultsButton(text="📢 Avval kanalga obuna bo'ling", start_parameter="sub"),
            )
        return None
