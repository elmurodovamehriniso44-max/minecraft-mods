import html
import logging
import re
import shutil
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from services import downloader, music, recognizer
from services.db import db

log = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")

URL_RE = re.compile(r"https?://[^\s]+", re.I)
IN_PROGRESS: set[tuple[int, str]] = set()


def _has_url(text: str) -> bool:
    return bool(URL_RE.search(text or ""))


# ---------------- 1) Havola -> Shazam -> MP3 ----------------
@router.message(F.text.func(_has_url))
async def on_link(message: Message, bot: Bot):
    url = URL_RE.search(message.text).group(0).rstrip(").,;")

    # Havola oldin qayta ishlangan bo'lsa, darhol yuboramiz
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
    rec = None
    try:
        async with music.SEM:
            audio, _info = await downloader.download_audio(
                url, workdir, bitrate="96", max_duration=config.MAX_LINK_SECONDS
            )
            await status.edit_text("🔎 Qo'shiq aniqlanmoqda...")
            rec = await recognizer.recognize(audio, workdir)
    except downloader.DownloadError as e:
        log.warning("Havola yuklanmadi %s: %s", url, e)
        await status.edit_text(
            "❌ Havoladan videoni yuklab bo'lmadi. Havola ochiq (public) ekanligini tekshiring."
        )
        return
    except Exception:
        log.exception("Havolani qayta ishlashda xato")
        await status.edit_text("❌ Kutilmagan xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if not rec:
        await status.edit_text("😕 Bu videodagi qo'shiqni aniqlab bo'lmadi.")
        return

    track_key = music.norm_key(rec.artist, rec.title)
    tr = await db.get_track(track_key)
    if tr:
        await db.save_link(url, track_key)
        await status.delete()
        await message.answer_audio(
            tr["file_id"], caption=f"🎧 {html.escape(rec.artist)} — {html.escape(rec.title)}"
        )
        return

    await status.edit_text(
        f"✅ Topildi: <b>{html.escape(rec.artist)} — {html.escape(rec.title)}</b>\n⏬ MP3 yuklanmoqda..."
    )
    prep = None
    try:
        targets = await music.targets_for_query(f"{rec.artist} - {rec.title}")
        prep = await music.prepare(targets, rec.title, rec.artist, rec.cover_url)
        fid = await music.send_prepared(bot, message.chat.id, prep)
        await db.save_track(track_key, fid, rec.title, rec.artist)
        await db.save_link(url, track_key)
        await status.delete()
    except Exception as e:
        log.warning("MP3 topilmadi: %s", e)
        await status.edit_text(
            f"🎵 <b>{html.escape(rec.artist)} — {html.escape(rec.title)}</b>\n\n"
            "Qo'shiq aniqlandi, lekin MP3 versiyasini yuklab bo'lmadi."
        )
    finally:
        if prep:
            prep.cleanup()


# ---------------- 2) Matn bilan qidiruv ----------------
@router.message(F.text, ~F.text.startswith("/"))
async def on_text(message: Message):
    query = message.text.strip()[:100]
    if len(query) < 2:
        await message.answer("Kamida 2 ta belgi yozing.")
        return
    wait = await message.answer("🔎 Qidirilmoqda...")
    try:
        results = await downloader.search(query, 10)
    except Exception:
        log.exception("Qidiruv xatosi")
        await wait.edit_text("❌ Qidiruvda xatolik. Keyinroq urinib ko'ring.")
        return
    if not results:
        await wait.edit_text("😕 Hech narsa topilmadi.")
        return

    rows = [
        [
            InlineKeyboardButton(
                text=f"{music.fmt_duration(r['duration'])} • {r['title'][:55]}",
                callback_data=f"dl:{r['id']}",
            )
        ]
        for r in results
    ]
    await wait.edit_text(
        f"🎶 <b>{html.escape(query)}</b> bo'yicha natijalar:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("dl:"))
async def on_download(cb: CallbackQuery, bot: Bot):
    vid = cb.data[3:]
    chat_id = cb.from_user.id
    guard = (chat_id, vid)
    if guard in IN_PROGRESS:
        await cb.answer("⏳ Allaqachon yuklanmoqda...")
        return
    await cb.answer("⏳ Yuklanmoqda...")

    tr = await db.get_track(f"yt:{vid}")
    if tr:  # Keshdan darhol
        await bot.send_audio(chat_id, tr["file_id"])
        return

    IN_PROGRESS.add(guard)
    status = await bot.send_message(chat_id, "⏬ Yuklanmoqda...")
    try:
        fid, sent = await music.ensure_youtube_cached(bot, vid, chat_id)
        if not sent:
            await bot.send_audio(chat_id, fid)
        await status.delete()
    except Exception as e:
        log.warning("Yuklash xatosi (%s): %s", vid, e)
        await status.edit_text("❌ Bu qo'shiqni yuklab bo'lmadi. Boshqa variantni tanlang.")
    finally:
        IN_PROGRESS.discard(guard)
