import html
import logging
import re
import shutil
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from handlers import ui
from services import catalog, downloader, music, recognizer, utils
from services.catalog import Item
from services.db import db

log = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")

URL_RE = re.compile(r"https?://[^\s]+", re.I)
IN_PROGRESS: set[tuple[int, str]] = set()
PAGE = 8


def _has_url(text: str) -> bool:
    return bool(URL_RE.search(text or ""))


def results_kb(items: list[Item], sid: str, page: int) -> InlineKeyboardMarkup:
    pages = max(1, -(-len(items) // PAGE))
    rows = [[InlineKeyboardButton(text=i.label, callback_data=i.cb)] for i in items[page * PAGE:(page + 1) * PAGE]]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"pg:{sid}:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"pg:{sid}:{page + 1}"))
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------- 1) Havola -> Shazam -> MP3 ----------------
@router.message(F.text.func(_has_url))
async def on_link(message: Message, bot: Bot):
    url = URL_RE.search(message.text).group(0).rstrip(").,;")

    key = await db.get_link(url)
    if key:
        tr = await db.get_track(key)
        if tr:
            await message.answer_audio(
                tr["file_id"], caption=f"🎧 {html.escape(tr['artist'])} — {html.escape(tr['title'])}"
            )
            return

    status = await message.answer("⏳ Havoladan audio olinmoqda...")
    workdir = Path(tempfile.mkdtemp(prefix="lnk_", dir=config.TMP_DIR))
    try:
        async with music.SEM:
            audio, _info = await downloader.download_audio(
                url, workdir, bitrate="96", max_duration=config.MAX_LINK_SECONDS
            )
            await status.edit_text("🔎 Qo'shiq aniqlanmoqda...")
            rec = await recognizer.recognize(audio, workdir)
    except downloader.DownloadError as e:
        log.warning("Havola yuklanmadi %s: %s", url, e)
        txt = "❌ Havoladan videoni yuklab bo'lmadi. Havola ochiq (public) ekanligini tekshiring."
        if message.from_user.id in config.ADMIN_IDS:
            txt += f"\n\n<code>{html.escape(utils.short_err(e))}</code>"
        await status.edit_text(txt)
        return
    except Exception:
        log.exception("Havolani qayta ishlashda xato")
        await status.edit_text("❌ Kutilmagan xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if not rec:
        await status.edit_text("😕 Bu videodagi qo'shiqni aniqlab bo'lmadi. Nomini yozib qidirib ko'ring.")
        return

    item = Item("d", "0", rec.title, rec.artist, None, rec.cover_url)
    await catalog.enrich(item)
    name = f"<b>{html.escape(rec.artist)} — {html.escape(rec.title)}</b>"
    await status.edit_text(f"✅ Topildi: {name}\n⏬ MP3 yuklanmoqda...")
    try:
        fid, sent, _ = await music.get_file_id(bot, item, message.chat.id)
        if not sent:
            await message.answer_audio(fid, caption=f"🎧 {html.escape(rec.artist)} — {html.escape(rec.title)}")
        await db.save_link(url, item.key)
        await status.delete()
    except Exception as e:
        log.warning("MP3 topilmadi: %s", e)
        txt = f"🎵 {name}\n\nQo'shiq aniqlandi, lekin MP3 versiyasini yuklab bo'lmadi."
        if message.from_user.id in config.ADMIN_IDS:
            txt += f"\n\n<code>{html.escape(utils.short_err(e))}</code>"
        await status.edit_text(txt)


# ---------------- 2) Qidiruv ----------------
async def _show(wait: Message, items: list[Item], title: str):
    sid = catalog.new_session(items)
    await wait.edit_text(
        f"{title}\nNatijalar: <b>{len(items)}</b> ta. Keraklisini tanlang 👇",
        reply_markup=results_kb(items, sid, 0),
    )


@router.message(F.text == ui.BTN_TOP)
async def on_top(message: Message):
    wait = await message.answer("🔥 Top musiqalar yuklanmoqda...")
    try:
        items = await catalog.chart(20)
    except Exception:
        log.exception("Chart xatosi")
        await wait.edit_text("❌ Top ro'yxatni olib bo'lmadi. Keyinroq urinib ko'ring.")
        return
    if not items:
        await wait.edit_text("😕 Ro'yxat bo'sh.")
        return
    await _show(wait, items, "🔥 <b>Top musiqalar</b>")


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(message: Message):
    query = message.text.strip()[:100]
    if len(query) < 2:
        await message.answer("Kamida 2 ta belgi yozing.")
        return
    wait = await message.answer("🔎 Qidirilmoqda...")
    try:
        items = await catalog.search(query)
    except Exception:
        log.exception("Qidiruv xatosi")
        await wait.edit_text("❌ Qidiruvda xatolik. Keyinroq urinib ko'ring.")
        return
    if not items:
        await wait.edit_text("😕 Hech narsa topilmadi. Boshqacha yozib ko'ring.")
        return
    await _show(wait, items, f"🎶 <b>{html.escape(query)}</b>")


@router.callback_query(F.data.startswith("pg:"))
async def on_page(cb: CallbackQuery):
    _, sid, page = cb.data.split(":")
    items = catalog.get_session(sid)
    if items is None:
        await cb.answer("Qidiruv eskirgan, qaytadan yozing.", show_alert=True)
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=results_kb(items, sid, int(page)))
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------------- 3) Tanlangan qo'shiqni yuklash ----------------
@router.callback_query(F.data.regexp(r"^[dy]:[\w\-]+$"))
async def on_download(cb: CallbackQuery, bot: Bot):
    kind, _, ident = cb.data.partition(":")
    chat_id = cb.from_user.id
    guard = (chat_id, cb.data)
    if guard in IN_PROGRESS:
        await cb.answer("⏳ Allaqachon yuklanmoqda...")
        return
    await cb.answer("⏳ Yuklanmoqda...")

    try:
        item = await catalog.resolve(kind, ident)
    except Exception:
        await bot.send_message(chat_id, "❌ Qo'shiq ma'lumotini olib bo'lmadi. Qaytadan qidiring.")
        return

    cached = await db.get_track(item.key)
    if cached:
        await bot.send_audio(chat_id, cached["file_id"])
        return

    IN_PROGRESS.add(guard)
    shown = f"{item.artist} — {item.title}" if item.kind == "d" else (item.title or "qo'shiq")
    status = await bot.send_message(chat_id, f"⏬ <b>{html.escape(shown)}</b>\nYuklanmoqda, biroz kuting...")
    try:
        fid, sent, preview = await music.get_file_id(bot, item, chat_id)
        if not sent:
            await bot.send_audio(chat_id, fid)
        await status.delete()
    except Exception as e:
        log.warning("Yuklash xatosi (%s): %s", cb.data, e)
        txt = "❌ Bu qo'shiqni hozir yuklab bo'lmadi. Ro'yxatdan boshqa variantni tanlang."
        if chat_id in config.ADMIN_IDS:
            txt += f"\n\n<b>Sabab (faqat admin):</b>\n<code>{html.escape(utils.short_err(e))}</code>\n\n/diag — tekshiruv"
        await status.edit_text(txt)
    finally:
        IN_PROGRESS.discard(guard)
