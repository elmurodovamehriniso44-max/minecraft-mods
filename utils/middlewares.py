"""Rate limit va foydalanuvchini ro'yxatga olish middleware'lari."""
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import config
from database import queries as q
from utils import texts as T


class ThrottleMiddleware(BaseMiddleware):
    """Oddiy sliding-window rate limiter (adminlar uchun o'chirilgan)."""

    def __init__(self) -> None:
        self._hits: Dict[int, deque] = defaultdict(deque)
        self._warned: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        if user is None or user.id in config.ADMIN_IDS:
            return await handler(event, data)

        now = time.monotonic()
        hits = self._hits[user.id]
        while hits and now - hits[0] > config.RATE_LIMIT_WINDOW:
            hits.popleft()

        if len(hits) >= config.RATE_LIMIT_COUNT:
            if isinstance(event, CallbackQuery):
                await event.answer(T.RATE_LIMIT)
            elif isinstance(event, Message):
                last = self._warned.get(user.id, 0.0)
                if now - last > config.RATE_LIMIT_WINDOW:
                    self._warned[user.id] = now
                    await event.answer(T.RATE_LIMIT)
            return None

        hits.append(now)
        if len(self._hits) > 5000:  # xotirani tozalash
            for uid in [u for u, d in self._hits.items() if not d]:
                self._hits.pop(uid, None)
        return await handler(event, data)


class UserTrackingMiddleware(BaseMiddleware):
    """Foydalanuvchini bazaga yozadi (jarayon davomida bir marta)."""

    def __init__(self) -> None:
        self._known: set = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        if user is not None and not user.is_bot and user.id not in self._known:
            await q.upsert_user(user.id, user.username, user.full_name)
            self._known.add(user.id)
        return await handler(event, data)
