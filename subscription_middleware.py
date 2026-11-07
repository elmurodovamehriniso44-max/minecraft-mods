"""Majburiy obuna tekshiruvi va tezlikni cheklash middleware'lari."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

CHECK_SUB_CB = "check_sub"
Channel = Union[int, str]


class SponsorshipCheckMiddleware(BaseMiddleware):
    def __init__(self, channels: List[Channel], redis: Optional[Redis] = None,
                 cache_ttl: int = 60) -> None:
        self.channels = channels
        self.redis = redis
        self.cache_ttl = cache_ttl
        self._link_cache: Dict[Channel, Tuple[str, Optional[str]]] = {}

    # ----------------------------------------------------------------- helpers
    async def _is_member(self, bot: Bot, channel: Channel, user_id: int) -> bool:
        try:
            member = await bot.get_chat_member(channel, user_id)
        except Exception as exc:
            # Bot kanalda admin emas / kanal topilmadi: foydalanuvchini bloklamaymiz.
            logger.error("get_chat_member failed for %s: %s", channel, exc)
            return True
        if member.status in ("left", "kicked"):
            return False
        if member.status == "restricted" and getattr(member, "is_member", True) is False:
            return False
        return True

    async def _missing_channels(self, bot: Bot, user_id: int) -> List[Channel]:
        cache_key = f"sub_ok:{user_id}"
        if self.redis is not None:
            try:
                if await self.redis.exists(cache_key):
                    return []
            except Exception as exc:
                logger.warning("Redis subscription cache read failed: %s", exc)

        flags = await asyncio.gather(
            *(self._is_member(bot, ch, user_id) for ch in self.channels)
        )
        missing = [ch for ch, ok in zip(self.channels, flags) if not ok]

        if not missing and self.redis is not None:
            try:
                await self.redis.set(cache_key, "1", ex=self.cache_ttl)
            except Exception as exc:
                logger.warning("Redis subscription cache write failed: %s", exc)
        return missing

    async def _channel_info(self, bot: Bot, channel: Channel) -> Tuple[str, Optional[str]]:
        if channel in self._link_cache:
            return self._link_cache[channel]
        title = str(channel)
        link: Optional[str] = None
        if isinstance(channel, str) and channel.startswith("@"):
            link = f"https://t.me/{channel[1:]}"
        try:
            chat = await bot.get_chat(channel)
            title = chat.title or title
            if chat.username:
                link = f"https://t.me/{chat.username}"
            elif getattr(chat, "invite_link", None):
                link = chat.invite_link
        except Exception as exc:
            logger.warning("get_chat failed for %s: %s", channel, exc)
        self._link_cache[channel] = (title, link)
        return title, link

    async def _build_markup(self, bot: Bot, missing: List[Channel]) -> InlineKeyboardMarkup:
        infos = await asyncio.gather(*(self._channel_info(bot, ch) for ch in missing))
        builder = InlineKeyboardBuilder()
        for title, link in infos:
            if link:
                builder.button(text=f"📢 {title}", url=link)
        builder.button(text="🔄 Obunani tekshirish", callback_data=CHECK_SUB_CB)
        builder.adjust(1)
        return builder.as_markup()

    # -------------------------------------------------------------------- main
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        bot: Bot = data["bot"]
        if not self.channels or user is None or user.is_bot:
            return await handler(event, data)

        is_check = isinstance(event, CallbackQuery) and event.data == CHECK_SUB_CB
        if is_check and self.redis is not None:
            try:  # "Tekshirish" bosilganda keshni chetlab o'tamiz
                await self.redis.delete(f"sub_ok:{user.id}")
            except Exception:
                pass

        missing = await self._missing_channels(bot, user.id)

        if not missing:
            if is_check:
                assert isinstance(event, CallbackQuery)
                await event.answer("✅ Rahmat! Endi botdan foydalanishingiz mumkin.")
                if isinstance(event.message, Message):
                    try:
                        await event.message.edit_text(
                            "✅ Obuna tasdiqlandi!\n\nQidirish uchun mod nomini yozing."
                        )
                    except Exception:
                        pass
                return None
            return await handler(event, data)

        text = (
            "🔒 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, "
            "so'ng «🔄 Obunani tekshirish» tugmasini bosing:"
        )
        markup = await self._build_markup(bot, missing)

        if isinstance(event, CallbackQuery):
            if is_check:
                await event.answer("❌ Hali barcha kanallarga obuna bo'lmagansiz.", show_alert=True)
            else:
                await event.answer()
                if isinstance(event.message, Message):
                    await event.message.answer(text, reply_markup=markup)
        elif isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        return None


class ThrottlingMiddleware(BaseMiddleware):
    """Redis asosidagi oddiy tezlik cheklovi (foydalanuvchi bo'yicha)."""

    def __init__(self, redis: Redis, limit: int = 8, window: int = 10) -> None:
        self.redis = redis
        self.limit = limit
        self.window = window

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        key = f"rl:{user.id}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window)
        except Exception as exc:
            logger.warning("Rate limit redis error: %s", exc)
            return await handler(event, data)

        if count <= self.limit:
            return await handler(event, data)

        if count == self.limit + 1:  # ogohlantirishni faqat bir marta yuboramiz
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ Juda tez! Biroz kuting.", show_alert=False)
            elif isinstance(event, Message):
                await event.answer("⏳ So'rovlar juda tez. Iltimos, biroz kuting.")
        elif isinstance(event, CallbackQuery):
            await event.answer()
        return None
