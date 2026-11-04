import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config

log = logging.getLogger(__name__)


async def get_unsubscribed(bot: Bot, user_id: int) -> list[str]:
    missing: list[str] = []
    for ch in config.CHANNELS:
        try:
            m = await bot.get_chat_member(ch, user_id)
            ok = m.status in ("creator", "administrator", "member") or (
                m.status == "restricted" and getattr(m, "is_member", False)
            )
            if not ok:
                missing.append(ch)
        except Exception as e:
            # Bot kanalda admin emas yoki kanal topilmadi: foydalanuvchini bloklamaymiz
            log.warning("Obuna tekshiruvi xatosi (%s): %s", ch, e)
    return missing


def subscribe_keyboard(channels: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in channels
    ]
    rows.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
