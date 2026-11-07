"""Maxsus filtrlar."""
from aiogram.filters import BaseFilter
from aiogram.types import Message, TelegramObject

import config


class IsAdmin(BaseFilter):
    """Faqat ADMIN_IDS ro'yxatidagi foydalanuvchilar uchun."""

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in config.ADMIN_IDS)


class PlainText(BaseFilter):
    """Buyruq bo'lmagan oddiy matn xabari."""

    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and not message.text.startswith("/")
