"""Admin buyruqlari: /stat va /broadcast."""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from services import db

log = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))


async def _stat_text() -> str:
    s = await db.stats()
    return (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>\n"
        f"🟢 Bugun faol: <b>{s['active_today']}</b>\n"
        f"🎵 Keshdagi (yuklangan) musiqalar: <b>{s['tracks']}</b>\n"
        f"📥 Jami yuborilgan audiolar: <b>{s['downloads']}</b>"
    )


@router.message(Command("stat"))
async def cmd_stat(message: Message):
    await message.answer(await _stat_text())


@router.message(F.text == config.BTN_ADMIN)
async def btn_admin(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm:stat")],
        [InlineKeyboardButton(text="📢 Xabar yuborish (yo'riqnoma)", callback_data="adm:bc")],
    ])
    await message.answer("⚙️ <b>Admin panel</b>", reply_markup=kb)


@router.callback_query(F.data == "adm:stat")
async def cb_stat(call: CallbackQuery):
    await call.answer()
    await call.message.answer(await _stat_text())


@router.callback_query(F.data == "adm:bc")
async def cb_bc(call: CallbackQuery):
    await call.answer()
    await call.message.answer(
        "📢 <b>Broadcast</b>\n\n"
        "• <code>/broadcast Matn</code> — oddiy matn yuboradi\n"
        "• Biror xabarga <b>reply</b> qilib <code>/broadcast</code> yozing — "
        "o'sha xabar (rasm, video, format bilan) hammaga nusxalanadi."
    )


async def _send_one(bot: Bot, uid: int, text: str | None, src: Message | None) -> bool:
    for _ in range(3):
        try:
            if src:
                await bot.copy_message(uid, src.chat.id, src.message_id)
            else:
                await bot.send_message(uid, text)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramAPIError:
            return False  # bot bloklangan / chat topilmadi va h.k.
        except Exception as e:
            log.warning("Broadcast xatosi %s: %s", uid, e)
            return False
    return False


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject, bot: Bot):
    src = message.reply_to_message
    text = (command.args or "").strip()
    if not src and not text:
        await message.answer("Foydalanish: <code>/broadcast Matn</code> yoki xabarga reply qilib /broadcast")
        return

    ids = await db.all_user_ids()
    status = await message.answer(f"📢 Yuborish boshlandi… (0/{len(ids)})")
    ok = fail = 0
    for i, uid in enumerate(ids, 1):
        if await _send_one(bot, uid, text, src):
            ok += 1
        else:
            fail += 1
        if i % 25 == 0:
            try:
                await status.edit_text(f"📢 Yuborilmoqda… ({i}/{len(ids)})")
            except TelegramAPIError:
                pass
        await asyncio.sleep(0.05)  # ~20 xabar/soniya (Telegram limiti 30 dan past)

    await status.edit_text(
        f"✅ <b>Broadcast tugadi</b>\n\nYuborildi: <b>{ok}</b>\nYetkazilmadi: <b>{fail}</b>"
    )
