import asyncio
import logging
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import config
from services.db import db

log = logging.getLogger(__name__)
router = Router()
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))


@router.message(Command("stat"))
async def cmd_stat(message: Message):
    s = await db.stats()
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{s['total']}</b>\n"
        f"🟢 So'nggi 24 soatda faol: <b>{s['active_24h']}</b>\n"
        f"🆕 So'nggi 24 soatda yangi: <b>{s['new_24h']}</b>\n"
        f"🚫 Botni bloklaganlar: <b>{s['blocked']}</b>\n"
        f"💾 Keshdagi treklar: <b>{s['tracks']}</b>"
    )


async def _deliver(bot: Bot, uid: int, src: Optional[Message], text: Optional[str]) -> None:
    if src:
        await bot.copy_message(uid, src.chat.id, src.message_id)
    else:
        await bot.send_message(uid, text)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject, bot: Bot):
    src = message.reply_to_message
    text = command.args
    if not src and not text:
        await message.answer(
            "Foydalanish:\n<code>/broadcast matn</code>\nyoki biror xabarga <b>reply</b> qilib /broadcast yozing."
        )
        return

    ids = await db.all_user_ids()
    status = await message.answer(f"📣 Yuborish boshlandi: {len(ids)} ta foydalanuvchi...")
    ok = fail = 0
    for uid in ids:
        try:
            try:
                await _deliver(bot, uid, src, text)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                await _deliver(bot, uid, src, text)
            ok += 1
        except TelegramForbiddenError:
            await db.mark_blocked(uid)
            fail += 1
        except Exception as e:
            log.warning("Broadcast xatosi (%s): %s", uid, e)
            fail += 1
        await asyncio.sleep(0.05)  # ~20 xabar/soniya (Telegram limiti ostida)
    await status.edit_text(f"✅ Tugadi.\nYuborildi: <b>{ok}</b>\nXato/bloklagan: <b>{fail}</b>")
