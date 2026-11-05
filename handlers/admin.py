import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

import config
from services import db, utils

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))

_tasks: set[asyncio.Task] = set()

BC_HELP = (
    "📣 <b>Broadcast</b>\n\n"
    "• <code>/broadcast matn</code> — matnni hammaga yuboradi\n"
    "• Istalgan xabarga (rasm, video, matn) <b>reply</b> qilib <code>/broadcast</code> yozing"
)


async def stat_text() -> str:
    return (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{await db.count_users()}</b>\n"
        f"✅ Faol: <b>{await db.count_active_users()}</b>\n"
        f"🆕 Bugun qo'shilgan: <b>{await db.count_new_today()}</b>\n"
        f"🎵 Yuklangan musiqalar (kesh): <b>{await db.count_tracks()}</b>\n"
        f"▶️ Jami yuborilgan: <b>{await db.total_plays()}</b>"
    )


@router.message(Command("stat"))
async def stat(message: Message) -> None:
    await message.answer(await stat_text())


@router.message(F.text == utils.BTN_ADMIN)
async def panel(message: Message) -> None:
    await message.answer("⚙️ <b>Admin panel</b>", reply_markup=utils.admin_panel_kb())


@router.callback_query(F.data == "adm:stat")
async def cb_stat(cb: CallbackQuery) -> None:
    await cb.answer()
    await cb.message.answer(await stat_text())


@router.callback_query(F.data == "adm:bc")
async def cb_bc(cb: CallbackQuery) -> None:
    await cb.answer()
    await cb.message.answer(BC_HELP)


async def _broadcast(bot: Bot, admin_chat: int, user_ids: list[int], text: str | None, src_id: int | None) -> None:
    ok = blocked = failed = 0

    async def send(uid: int) -> None:
        nonlocal ok, blocked, failed
        for _ in range(2):
            try:
                if src_id:
                    await bot.copy_message(uid, admin_chat, src_id)
                else:
                    await bot.send_message(uid, text)
                ok += 1
                return
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except TelegramForbiddenError:
                blocked += 1
                await db.set_inactive(uid)
                return
            except TelegramAPIError:
                failed += 1
                return
        failed += 1

    for i in range(0, len(user_ids), 25):  # Telegram limiti: ~30 xabar/soniya
        await asyncio.gather(*(send(u) for u in user_ids[i : i + 25]))
        await asyncio.sleep(1)
    try:
        await bot.send_message(
            admin_chat,
            f"📣 <b>Broadcast tugadi</b>\n\n✅ Yuborildi: {ok}\n🚫 Bloklagan: {blocked}\n⚠️ Xato: {failed}",
        )
    except Exception:
        logger.exception("Broadcast hisobotini yuborib bo'lmadi")


@router.message(Command("broadcast"))
async def broadcast(message: Message, command: CommandObject, bot: Bot) -> None:
    src = message.reply_to_message
    text = (command.args or "").strip()
    if not src and not text:
        await message.answer(BC_HELP)
        return
    ids = await db.get_active_user_ids()
    await message.answer(f"🚀 Broadcast boshlandi: {len(ids)} ta foydalanuvchi.")
    task = asyncio.create_task(
        _broadcast(bot, message.chat.id, ids, None if src else text, src.message_id if src else None)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
