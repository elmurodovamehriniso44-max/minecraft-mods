import asyncio
import html
import logging
import re
import time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender

import config
from services import db, downloader, recognizer, tagger, utils
from services.utils import esc

logger = logging.getLogger(__name__)
router = Router()

_sem = asyncio.Semaphore(config.MAX_PARALLEL_JOBS)
_locks: dict[str, asyncio.Lock] = {}
_busy_users: set[int] = set()
_last_alert = 0.0

GENERIC_ERR = (
    "😔 Kechirasiz, qo'shiqni olib bo'lmadi. Manba yoki internet bilan muammo bo'lishi mumkin — "
    "birozdan so'ng qayta urinib ko'ring."
)


# ---------------- yordamchilar ----------------
async def _caption(bot: Bot) -> str:
    return f"🎧 @{(await bot.me()).username}"


async def _safe_send(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        logger.debug("Xabar yuborib bo'lmadi", exc_info=True)


async def _alert_admins(bot: Bot, text: str) -> None:
    """YouTube bloklasa adminlarga (30 daqiqada bir marta) xabar beradi."""
    global _last_alert
    if time.time() - _last_alert < 1800:
        return
    _last_alert = time.time()
    for admin_id in config.ADMIN_IDS:
        await _safe_send(bot, admin_id, text)


async def _send_cached(bot: Bot, chat_id: int, row) -> bool:
    """file_id orqali darhol yuboradi. file_id yaroqsiz bo'lsa keshdan o'chiradi va False qaytaradi."""
    try:
        await bot.send_audio(
            chat_id,
            audio=row["file_id"],
            caption=await _caption(bot),
            protect_content=config.PROTECT_CONTENT,
        )
        await db.inc_plays(row["key"])
        return True
    except TelegramForbiddenError:
        return True  # foydalanuvchi botni bloklagan
    except TelegramBadRequest as e:
        if "identifier" in str(e).lower() or "wrong file" in str(e).lower():
            logger.warning("Yaroqsiz file_id, keshdan o'chirilmoqda: %s", row["key"])
            await db.delete_track(row["key"])
            return False
        raise


def _safe_filename(artist: str, title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "", f"{artist} - {title}").strip()[:100] + ".mp3"


async def _fetch_tag_send(bot, chat_id, tmp, keys, artist, title, video_id, cover_url) -> None:
    f = await downloader.fetch_track(tmp, artist, title, video_id)
    artist, title = artist or f.artist, title or f.title

    raw = await utils.fetch_bytes(cover_url)
    if not raw and f.source == "youtube":
        raw = await utils.fetch_bytes(downloader.thumb_url(f.source_id))
    cover = await asyncio.to_thread(tagger.prepare_cover, raw)
    await asyncio.to_thread(tagger.tag_mp3, f.path, title, artist, cover)
    thumb = await asyncio.to_thread(tagger.make_thumb, cover)

    msg = await bot.send_audio(
        chat_id,
        audio=FSInputFile(f.path, filename=_safe_filename(artist, title)),
        title=title,
        performer=artist,
        duration=f.duration or None,
        thumbnail=BufferedInputFile(thumb, "cover.jpg") if thumb else None,
        caption=await _caption(bot),
        protect_content=config.PROTECT_CONTENT,
    )
    file_id = msg.audio.file_id
    save_keys = list(dict.fromkeys([*keys, *([f.source_id] if f.source == "youtube" and f.source_id else [])]))
    for k in save_keys:
        await db.save_track(k, title, artist, f.duration, file_id)
    await db.inc_plays(keys[0])


async def process(bot, chat_id, keys, *, artist=None, title=None, video_id=None, cover_url=None, status=None) -> bool:
    """Yuklash -> teg -> yuborish -> keshga yozish. Hech qachon exception ko'tarmaydi."""
    primary = keys[0]
    lock = _locks.setdefault(primary, asyncio.Lock())
    try:
        if status is None:
            status = await bot.send_message(chat_id, "⏳ Qo'shiq tayyorlanmoqda, bir zum...")
        async with ChatActionSender.upload_voice(bot=bot, chat_id=chat_id):
            async with lock:
                row = await db.get_track(primary)  # navbat kutganda boshqasi yuklab bo'lgan bo'lishi mumkin
                if row and await _send_cached(bot, chat_id, row):
                    return True
                async with _sem:
                    tmp = utils.make_workdir()
                    try:
                        await _fetch_tag_send(bot, chat_id, tmp, keys, artist, title, video_id, cover_url)
                    finally:
                        utils.rmtree(tmp)
        return True
    except downloader.TooLong:
        await _safe_send(bot, chat_id, f"⏱ Bu qo'shiq juda uzun (maksimum {config.TRACK_MAX_DURATION // 60} daqiqa).")
    except downloader.TooBig:
        await _safe_send(bot, chat_id, "📦 Fayl hajmi Telegram limitidan katta.")
    except TelegramForbiddenError:
        pass
    except asyncio.TimeoutError:
        await _safe_send(bot, chat_id, "⌛ Yuklash juda uzoq davom etdi. Keyinroq urinib ko'ring.")
    except downloader.DownloaderError as e:
        logger.warning("Yuklash xatosi (%s): %s", primary, e)
        if downloader.looks_blocked(e):
            await _alert_admins(bot, "⚠️ YouTube bloklayapti. cookies.txt ni yangilang (Render → Secret Files).")
        await _safe_send(bot, chat_id, GENERIC_ERR)
    except Exception:
        logger.exception("process xatolik: %s", primary)
        await _safe_send(bot, chat_id, GENERIC_ERR)
    finally:
        if status:
            try:
                await status.delete()
            except Exception:
                pass
        if not lock.locked():
            _locks.pop(primary, None)
    return False


async def deliver_by_key(bot: Bot, chat_id: int, key: str) -> None:
    """Tugma/deep-link orqali kelgan kalit bo'yicha: avval keshdan, bo'lmasa yuklab."""
    if not utils.KEY_RE.match(key):
        await _safe_send(bot, chat_id, "❌ Noto'g'ri havola.")
        return
    artist = title = None
    try:
        row = await db.get_track(key)
        if row:
            if await _send_cached(bot, chat_id, row):
                return
            artist, title = row["artist"], row["title"]
    except Exception:
        logger.exception("Keshdan yuborishda xatolik")

    if utils.YT_ID_RE.match(key):
        a, t = downloader.recall(key)
        await process(bot, chat_id, [key], artist=artist or a, title=title or t, video_id=key)
    elif key.startswith("sz_") and artist and title:
        await process(bot, chat_id, [key], artist=artist, title=title)
    else:
        await _safe_send(bot, chat_id, "😕 Bu qo'shiq endi mavjud emas. Iltimos, qaytadan qidiring.")


# ---------------- havoladan Shazam ----------------
async def handle_link(message: Message, bot: Bot, url: str) -> None:
    uid, chat_id = message.from_user.id, message.chat.id
    if uid in _busy_users:
        await message.answer("⏳ Oldingi so'rovingiz hali tugamadi. Biroz kuting.")
        return
    _busy_users.add(uid)
    status: Message | None = None

    async def final(text: str) -> None:
        nonlocal status
        await utils.safe_edit(status, text)
        status = None

    try:
        norm = utils.normalize_url(url)
        known = await db.get_link(norm)
        if known:
            row = await db.get_track(known)
            if row and await _send_cached(bot, chat_id, row):
                return

        status = await message.answer("🔗 Havola qabul qilindi, audio olinmoqda...")
        async with ChatActionSender.upload_voice(bot=bot, chat_id=chat_id):
            tmp = utils.make_workdir()
            try:
                async with _sem:
                    src = await downloader.download_source_audio(url, tmp)
                    await utils.safe_edit(status, "🎼 Qo'shiq aniqlanmoqda...")
                    rec = await recognizer.recognize(src, tmp)
            finally:
                utils.rmtree(tmp)

        if not rec:
            await final("😕 Qo'shiqni aniqlab bo'lmadi. Videoda musiqa aniq eshitilmasligi yoki original ovoz bo'lishi mumkin.")
            return

        key = f"sz_{rec.key}"
        row = await db.get_track(key)
        if row and await _send_cached(bot, chat_id, row):
            await db.set_link(norm, key)
            return

        await utils.safe_edit(
            status, f"✅ Topildi: <b>{esc(rec.artist)} — {esc(rec.title)}</b>\n⬇️ To'liq variant yuklanmoqda..."
        )
        ok = await process(
            bot, chat_id, [key], artist=rec.artist, title=rec.title, cover_url=rec.cover_url, status=status
        )
        status = None  # process() uni o'zi o'chiradi
        if ok:
            await db.set_link(norm, key)
    except downloader.TooLong:
        await final(f"⏱ Video juda uzun (maksimum {config.LINK_MAX_DURATION // 60} daqiqa).")
    except downloader.DownloaderError as e:
        logger.warning("Havola xatosi (%s): %s", url, str(e)[:300])
        if downloader.looks_blocked(e):
            await _alert_admins(bot, "⚠️ Havoladan yuklashda blok/login xatosi. cookies.txt ni yangilang.")
        await final("😔 Havoladan audio olib bo'lmadi. Havola yopiq (private) bo'lishi yoki qo'llab-quvvatlanmasligi mumkin.")
    except asyncio.TimeoutError:
        await final("⌛ So'rov juda uzoq davom etdi. Keyinroq urinib ko'ring.")
    except TelegramForbiddenError:
        pass
    except Exception:
        logger.exception("handle_link xatolik")
        await final(GENERIC_ERR)
    finally:
        _busy_users.discard(uid)
        if status:
            try:
                await status.delete()
            except Exception:
                pass


# ---------------- matnli qidiruv ----------------
@router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot) -> None:
    text = message.text.strip()
    url = utils.extract_url(text)
    if url:
        await handle_link(message, bot, url)
        return
    if len(text) < 2:
        await message.answer("✏️ Kamida 2 ta belgidan iborat nom yozing yoki havola yuboring.")
        return

    try:
        async with ChatActionSender.upload_voice(bot=bot, chat_id=message.chat.id):
            cached_rows = await db.search_tracks(text, limit=10)
            try:
                yt = await downloader.search_youtube(text)
            except Exception as e:
                logger.warning("YouTube qidiruv xatosi: %s", str(e)[:200])
                yt = []
            have = await db.get_tracks([r.video_id for r in yt])
    except Exception:
        logger.exception("Qidiruvda xatolik: %s", text)
        await message.answer("😔 Qidiruvda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
        return

    items: list[tuple] = [(r["key"], r["artist"], r["title"], True) for r in cached_rows]
    seen = {r["file_id"] for r in cached_rows}
    for r in yt:
        row = have.get(r.video_id)
        if row and row["file_id"] in seen:
            continue
        if row:
            seen.add(row["file_id"])
        items.append((r.video_id, r.artist, r.title, bool(row)))

    if not items:
        await message.answer("😕 Hech narsa topilmadi. Ijrochi va nomini birga yozib ko'ring.")
        return

    token = utils.STORE.put(items)
    await message.answer(
        f"🔎 <b>{esc(text)}</b> bo'yicha {len(items)} ta natija:\n⚡ — tayyor, bir zumda yuboriladi",
        reply_markup=utils.paginate_kb(items, 0, lambda p: f"pg:{token}:{p}"),
    )


@router.callback_query(F.data.startswith("pg:"))
async def on_page(cb: CallbackQuery) -> None:
    try:
        _, token, page = cb.data.split(":")
        items = utils.STORE.get(token)
        if items is None:
            await cb.answer("Qidiruv eskirgan. Qaytadan yozing 🔍", show_alert=True)
            return
        await cb.message.edit_reply_markup(
            reply_markup=utils.paginate_kb(items, int(page), lambda p: f"pg:{token}:{p}")
        )
        await cb.answer()
    except TelegramBadRequest:
        await cb.answer()
    except Exception:
        logger.exception("Sahifalashda xatolik")
        await cb.answer()


# ---------------- Top musiqalar ----------------
async def _top_items() -> list[tuple]:
    return [(r["key"], r["artist"], r["title"], True) for r in await db.top_tracks(30)]


@router.message(Command("top"))
@router.message(F.text == utils.BTN_TOP)
async def on_top(message: Message) -> None:
    items = await _top_items()
    if not items:
        await message.answer("🔥 Top ro'yxat hali shakllanmagan. Birinchi bo'lib qo'shiq qidiring!")
        return
    await message.answer("🔥 <b>Top musiqalar</b>", reply_markup=utils.paginate_kb(items, 0, lambda p: f"tp:{p}"))


@router.callback_query(F.data.startswith("tp:"))
async def on_top_page(cb: CallbackQuery) -> None:
    try:
        items = await _top_items()
        await cb.message.edit_reply_markup(
            reply_markup=utils.paginate_kb(items, int(cb.data[3:]), lambda p: f"tp:{p}")
        )
    except TelegramBadRequest:
        pass
    except Exception:
        logger.exception("Top sahifalashda xatolik")
    await cb.answer()


# ---------------- umumiy callback'lar ----------------
@router.callback_query(F.data.startswith("dl:"))
async def on_download(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer("⏳ Tayyorlanmoqda...")
    await deliver_by_key(bot, cb.from_user.id, cb.data[3:])


@router.callback_query(F.data == "noop")
async def on_noop(cb: CallbackQuery) -> None:
    await cb.answer()
