import asyncio
import logging
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, Message

import config
from handlers import ui
from services import diag
from services.db import db

log = logging.getLogger(__name__)
router = Router()
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))

BG_TASKS: set[asyncio.Task] = set()
PANEL_TEXT = "⚙️ <b>Admin panel</b>\n\nKerakli bo'limni tanlang:"


class AdminSt(StatesGroup):
    broadcast = State()
    add_channel = State()


def panel_kb() -> Kb:
    return Kb(
        inline_keyboard=[
            [Btn(text="📊 Statistika", callback_data="adm:stat"), Btn(text="🩺 Diagnostika", callback_data="adm:diag")],
            [Btn(text="📣 Xabar yuborish", callback_data="adm:bc"), Btn(text="📢 Majburiy obuna", callback_data="adm:subs")],
            [Btn(text="🧹 Keshni tozalash", callback_data="adm:clr")],
            [Btn(text="❌ Yopish", callback_data="adm:close")],
        ]
    )


def back_kb() -> Kb:
    return Kb(inline_keyboard=[[Btn(text="⬅️ Orqaga", callback_data="adm:home")]])


async def _edit(cb: CallbackQuery, text: str, kb: Optional[Kb] = None) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


# ---------------- Kirish ----------------
@router.message(Command("admin"))
@router.message(F.text == ui.BTN_ADMIN)
async def open_panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(PANEL_TEXT, reply_markup=panel_kb())


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=panel_kb())


@router.callback_query(F.data == "adm:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _edit(cb, PANEL_TEXT, panel_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:close")
async def cb_close(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()


# ---------------- Statistika ----------------
async def _stat_text() -> str:
    s = await db.stats()
    return (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{s['total']}</b>\n"
        f"🟢 So'nggi 24 soatda faol: <b>{s['active_24h']}</b>\n"
        f"🆕 So'nggi 24 soatda yangi: <b>{s['new_24h']}</b>\n"
        f"🚫 Botni bloklaganlar: <b>{s['blocked']}</b>\n"
        f"💾 Keshdagi treklar: <b>{s['tracks']}</b>"
    )


@router.message(Command("stat"))
async def cmd_stat(message: Message):
    await message.answer(await _stat_text())


@router.callback_query(F.data == "adm:stat")
async def cb_stat(cb: CallbackQuery):
    await _edit(cb, await _stat_text(), back_kb())
    await cb.answer()


# ---------------- Diagnostika ----------------
@router.message(Command("diag"))
async def cmd_diag(message: Message):
    wait = await message.answer("⏳ Tekshirilmoqda (1 daqiqagacha)...")
    await wait.edit_text(await diag.run())


@router.callback_query(F.data == "adm:diag")
async def cb_diag(cb: CallbackQuery):
    await cb.answer()
    await _edit(cb, "⏳ Tekshirilmoqda (1 daqiqagacha)...")
    await _edit(cb, await diag.run(), back_kb())


# ---------------- Kesh ----------------
@router.callback_query(F.data == "adm:clr")
async def cb_clr(cb: CallbackQuery):
    kb = Kb(inline_keyboard=[[Btn(text="✅ Ha, tozalash", callback_data="adm:clr_yes"), Btn(text="⬅️ Yo'q", callback_data="adm:home")]])
    await _edit(cb, "🧹 Barcha keshlangan treklar o'chiriladi (bot qayta yuklab oladi). Davom etamizmi?", kb)
    await cb.answer()


@router.callback_query(F.data == "adm:clr_yes")
async def cb_clr_yes(cb: CallbackQuery):
    n = await db.clear_tracks()
    await _edit(cb, f"✅ {n} ta trek keshdan o'chirildi.", back_kb())
    await cb.answer()


# ---------------- Majburiy obuna ----------------
async def _subs_view(cb_or_msg) -> tuple[str, Kb]:
    chans = await db.get_channels()
    state = "🟢 yoqilgan" if chans else "🔴 o'chirilgan (kanal yo'q)"
    rows = [[Btn(text=f"❌ {ch}", callback_data=f"adm:rm:{i}")] for i, ch in enumerate(chans)]
    rows.append([Btn(text="➕ Kanal qo'shish", callback_data="adm:add")])
    rows.append([Btn(text="⬅️ Orqaga", callback_data="adm:home")])
    text = f"📢 <b>Majburiy obuna</b>: {state}\n\nKanalni o'chirish uchun ustiga bosing.\nBot kanalda <b>admin</b> bo'lishi shart."
    return text, Kb(inline_keyboard=rows)


@router.callback_query(F.data == "adm:subs")
async def cb_subs(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = await _subs_view(cb)
    await _edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:rm:"))
async def cb_rm(cb: CallbackQuery):
    idx = int(cb.data.split(":")[2])
    chans = await db.get_channels()
    if 0 <= idx < len(chans):
        chans.pop(idx)
        await db.set_channels(chans)
    text, kb = await _subs_view(cb)
    await _edit(cb, text, kb)
    await cb.answer("O'chirildi")


@router.callback_query(F.data == "adm:add")
async def cb_add(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.add_channel)
    await _edit(cb, "➕ Kanal username'ini yuboring (masalan <code>@kanalim</code>).\nBekor qilish: /cancel", None)
    await cb.answer()


@router.message(AdminSt.add_channel, F.text)
async def msg_add_channel(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip().replace("https://t.me/", "").replace("t.me/", "").lstrip("@")
    ch = "@" + raw
    try:
        await bot.get_chat(ch)
        me = await bot.me()
        m = await bot.get_chat_member(ch, me.id)
        if m.status not in ("administrator", "creator"):
            await message.answer("❌ Bot bu kanalda admin emas. Avval botni admin qiling, so'ng qayta yuboring.")
            return
    except Exception:
        await message.answer("❌ Kanal topilmadi yoki bot unga kira olmaydi. Username'ni tekshiring.")
        return
    chans = await db.get_channels()
    if ch not in chans:
        chans.append(ch)
        await db.set_channels(chans)
    await state.clear()
    text, kb = await _subs_view(message)
    await message.answer(f"✅ {ch} qo'shildi.\n\n{text}", reply_markup=kb)


# ---------------- Xabar yuborish ----------------
async def _deliver(bot: Bot, uid: int, src_chat: Optional[int], src_msg: Optional[int], text: Optional[str]) -> None:
    if src_msg:
        await bot.copy_message(uid, src_chat, src_msg)
    else:
        await bot.send_message(uid, text)


async def run_broadcast(bot: Bot, status: Message, src_chat: Optional[int], src_msg: Optional[int], text: Optional[str]):
    ids = await db.all_user_ids()
    ok = fail = 0
    for i, uid in enumerate(ids, 1):
        try:
            try:
                await _deliver(bot, uid, src_chat, src_msg, text)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                await _deliver(bot, uid, src_chat, src_msg, text)
            ok += 1
        except TelegramForbiddenError:
            await db.mark_blocked(uid)
            fail += 1
        except Exception as e:
            log.warning("Broadcast xatosi (%s): %s", uid, e)
            fail += 1
        if i % 50 == 0:
            try:
                await status.edit_text(f"📣 Yuborilmoqda... {i}/{len(ids)}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    try:
        await status.edit_text(f"✅ Yuborish tugadi.\nYetkazildi: <b>{ok}</b>\nXato/bloklagan: <b>{fail}</b>")
    except Exception:
        pass


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    BG_TASKS.add(t)
    t.add_done_callback(BG_TASKS.discard)


@router.callback_query(F.data == "adm:bc")
async def cb_bc(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.broadcast)
    await _edit(
        cb,
        "📣 Yubormoqchi bo'lgan xabaringizni yuboring (matn, rasm, video — istalgani).\nBekor qilish: /cancel",
        None,
    )
    await cb.answer()


@router.message(AdminSt.broadcast)
async def msg_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(chat_id=message.chat.id, msg_id=message.message_id)
    n = len(await db.all_user_ids())
    await message.answer("👆 Xabar shunday ko'rinadi.")
    await bot.copy_message(message.chat.id, message.chat.id, message.message_id)
    kb = Kb(inline_keyboard=[[Btn(text=f"✅ Yuborish ({n} ta)", callback_data="adm:bc_go"), Btn(text="❌ Bekor", callback_data="adm:home")]])
    await message.answer("Hammaga yuborilsinmi?", reply_markup=kb)


@router.callback_query(F.data == "adm:bc_go")
async def cb_bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    if not data.get("msg_id"):
        await cb.answer("Xabar topilmadi", show_alert=True)
        return
    await cb.answer("Boshlandi")
    status = await cb.message.answer("📣 Yuborish boshlandi...")
    _spawn(run_broadcast(bot, status, data["chat_id"], data["msg_id"], None))


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject, bot: Bot):
    src = message.reply_to_message
    if not src and not command.args:
        await message.answer("Foydalanish: xabarga reply qilib /broadcast yozing yoki «⚙️ Admin panel → 📣 Xabar yuborish» dan foydalaning.")
        return
    status = await message.answer("📣 Yuborish boshlandi...")
    _spawn(run_broadcast(bot, status, src.chat.id if src else None, src.message_id if src else None, command.args))
