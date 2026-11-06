"""Majburiy obuna va tezlik cheklash middleware'lari."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional, Union

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

logger = logging.getLogger(__name__)

CHECK_SUB_CB = "check_sub"
_MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}

ChannelId = Union[int, str]


class SponsorshipCheckMiddleware(BaseMiddleware):
    def __init__(
        self,
        channels: list[ChannelId],
        redis: Any = None,
        cache_ttl: int = 60,
    ) -> None:
        self.channels = channels
        self.redis = redis
        self.cache_ttl = cache_ttl
        self._links: dict[ChannelId, tuple[str, Optional[str]]] = {}

    # ---------------------------------------------------------------- helpers
    async def _is_member(self, bot: Bot, user_id: int, channel: ChannelId) -> bool:
        cache_key = f"sub:{user_id}:{channel}"
        if self.redis is not None:
            try:
                if await self.redis.get(cache_key):
                    return True
            except Exception:
                logger.warning("Redis obuna keshi xatosi", exc_info=True)

        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        except Exception as exc:
            # Bot kanalda admin emas / kanal topilmadi: foydalanuvchilarni
            # qulflab qo'ymaslik uchun o'tkazib yuboramiz, lekin log yozamiz.
            logger.error("get_chat_member xatosi (%s): %s", channel, exc)
            return True

        is_member = member.status in _MEMBER_STATUSES or (
            member.status == ChatMemberStatus.RESTRICTED
            and getattr(member, "is_member", False)
        )
        if is_member and self.redis is not None:
            try:
                await self.redis.set(cache_key, "1", ex=self.cache_ttl)
            except Exception:
                logger.warning("Redis obuna keshi yozish xatosi", exc_info=True)
        return is_member

    async def _missing_channels(self, bot: Bot, user_id: int) -> list[ChannelId]:
        results = await asyncio.gather(
            *(self._is_member(bot, user_id, ch) for ch in self.channels)
        )
        return [ch for ch, ok in zip(self.channels, results) if not ok]

    async def _channel_info(
        self, bot: Bot, channel: ChannelId
    ) -> tuple[str, Optional[str]]:
        """(sarlavha, havola) qaytaradi."""
        if channel in self._links:
            return self._links[channel]

        title: str = str(channel)
        link: Optional[str] = None
        if isinstance(channel, str) and channel.startswith("@"):
            link = f"https://t.me/{channel[1:]}"
        try:
            chat = await bot.get_chat(channel)
            title = chat.title or title
            if chat.username:
                link = f"https://t.me/{chat.username}"
            elif chat.invite_link:
                link = chat.invite_link
            elif link is None:
                link = await bot.export_chat_invite_link(chat.id)
        except Exception as exc:
            logger.warning("Kanal ma'lumotini olib bo'lmadi (%s): %s", channel, exc)

        self._links[channel] = (title, link)
        return title, link

    async def _build_keyboard(
        self, bot: Bot, missing: list[ChannelId]
    ) -> InlineKeyboardMarkup:
        infos = await asyncio.gather(*(self._channel_info(bot, ch) for ch in missing))
        rows = [
            [InlineKeyboardButton(text=f"📢 {title}", url=link)]
            for title, link in infos
            if link
        ]
        rows.append(
            [InlineKeyboardButton(text="🔄 Obunani tekshirish", callback_data=CHECK_SUB_CB)]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    # ------------------------------------------------------------------- main
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot or not self.channels:
            return await handler(event, data)

        bot: Bot = data["bot"]
        is_check = isinstance(event, CallbackQuery) and event.data == CHECK_SUB_CB
        missing = await self._missing_channels(bot, user.id)

        if not missing:
            if is_check:
                assert isinstance(event, CallbackQuery)
                await event.answer("✅ Obuna tasdiqlandi!")
                if isinstance(event.message, Message):
                    try:
                        await event.message.edit_text(
                            "✅ Rahmat! Endi qidirish uchun mod yoki addon nomini yozing."
                        )
                    except Exception:
                        pass
                return None
            return await handler(event, data)

        text = (
            "🔒 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, "
            "so'ng «🔄 Obunani tekshirish» tugmasini bosing:"
        )
        keyboard = await self._build_keyboard(bot, missing)

        if isinstance(event, CallbackQuery):
            if is_check:
                await event.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz.", show_alert=True)
                if isinstance(event.message, Message):
                    try:
                        await event.message.edit_reply_markup(reply_markup=keyboard)
                    except Exception:
                        pass
            else:
                await event.answer("Avval kanallarga obuna bo'ling.", show_alert=True)
                if isinstance(event.message, Message):
                    await event.message.answer(text, reply_markup=keyboard)
        elif isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard)
        return None


class ThrottlingMiddleware(BaseMiddleware):
    """Redis asosidagi oddiy fixed-window tezlik cheklovi."""

    def __init__(self, redis: Any, limit: int = 6, window: int = 5) -> None:
        self.redis = redis
        self.limit = limit
        self.window = window

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        key = f"rl:{user.id}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window)
        except Exception:
            logger.warning("Rate-limit Redis xatosi", exc_info=True)
            return await handler(event, data)

        if count > self.limit:
            if count == self.limit + 1:  # ogohlantirishni faqat bir marta yuboramiz
                if isinstance(event, CallbackQuery):
                    await event.answer("⏳ Juda tez! Biroz kuting.", show_alert=False)
                elif isinstance(event, Message):
                    await event.answer("⏳ So'rovlar juda tez. Iltimos, bir necha soniya kuting.")
            elif isinstance(event, CallbackQuery):
                await event.answer()
            return None
        return await handler(event, data)
