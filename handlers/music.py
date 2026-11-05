"""Spotify havola tahlili, matnli qidiruv (10 variant), yuklash va callback'lar."""
import asyncio
import logging
import time
import uuid

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    BufferedInputFile, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InputMediaAudio, Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from services import db, deezer, downloader, spotifier, tagger, utils
from services.downloader import DownloadError
from services.spotifier import SpotifyError, TrackInfo

log = logging.getLogger(__name__)
router = Router(name="music")

TOTAL_RESULTS = 10     # Spotify bitta so'rovda maksimum 10 ta natija beradi

_locks: dict[str, asyncio.Lock] = {}   # bir xil trek ikki marta yuklanmasligi uchun
_album_busy: set[int] = set()
_yt_results: dict[str, dict] = {}      # sid -> {"ts": vaqt, "items": {idx: variant}}


# =============================================================================
#  Asosiy mantiq: kesh -> yuklash -> teg -> yuborish -> keshga yozish
# =============================================================================
def _row_name(row: dict) -> str:
    return f"{row['artist']} — {row['title']}" if row.get("artist") else row["title"]


async def _send_cached(bot: Bot, chat_id: int, user_id: int, row: dict) -> Message | None:
    try:
        msg = await bot.send_audio(chat_id, row["file_id"], caption=await utils.bot_caption(bot))
    except TelegramBadRequest as e:
        log.warning("Keshdagi file_id yaroqsiz (id=%s): %s", row["id"], e)
        return None
    await db.register_download(user_id, row["id"])
    return msg


async def send_track(bot: Bot, chat_id: int, user_id: int, track: TrackInfo,
                     source_url: str | None = None) -> Message:
    """Trekni chatga yuboradi. Avval kesh, bo'lmasa yuklab oladi. source_url — tanlangan aniq variant."""
    row = await db.find_cached(track.spotify_id, track.cache_key)
    if row and (msg := await _send_cached(bot, chat_id, user_id, row)):
        return msg

    lock = _locks.setdefault(track.cache_key or track.title, asyncio.Lock())
    async with lock:
        row = await db.find_cached(track.spotify_id, track.cache_key)  # kutish paytida boshqasi yuklagan bo'lishi mumkin
        if row and (msg := await _send_cached(bot, chat_id, user_id, row)):
            return msg

        query = f"{track.artist} - {track.title}" if track.artist else track.title
        t0 = time.monotonic()
        # Muqova audio bilan parallel yuklanadi (vaqt tejaladi)
        cover_task = asyncio.create_task(utils.download_bytes(track.cover_url)) if track.cover_url else None
        try:
            path = await downloader.download_audio(query, track.duration_s, url=source_url)
        except BaseException:
            if cover_task:
                cover_task.cancel()
            raise
        t1 = time.monotonic()
        try:
            cover = await cover_task if cover_task else None
            await asyncio.to_thread(tagger.tag_mp3, path, track.title, track.artist or None, track.album, cover)
            duration = await asyncio.to_thread(tagger.get_duration, path) or track.duration_s
            thumb = BufferedInputFile(cover, "cover.jpg") if cover and len(cover) < 200 * 1024 else None

            msg = await bot.send_audio(
                chat_id,
                FSInputFile(path, filename=f"{utils.sanitize_filename(track.display)}.mp3"),
                title=track.title,
                performer=track.artist or None,
                duration=duration,
                thumbnail=thumb,
                caption=await utils.bot_caption(bot),
            )
            log.info("⏱ '%s': yuklash+konvertatsiya %.1fs, Telegramga yuborish %.1fs",
                     track.display[:50], t1 - t0, time.monotonic() - t1)
            track_id = await db.save_track(
                cache_key=track.cache_key or utils.normalize_key(track.title),
                spotify_id=track.spotify_id, artist=track.artist, title=track.title,
                album=track.album, cover_url=track.cover_url, duration=duration,
                file_id=msg.audio.file_id,
            )
            await db.register_download(user_id, track_id)
            return msg
        finally:
            utils.safe_unlink(path)


async def _fail(bot: Bot, chat_id: int, status: Message | None, text: str) -> None:
    try:
        if status:
            await status.edit_text(text)
        else:
            await bot.send_message(chat_id, text)
    except TelegramAPIError:
        pass


async def deliver(bot: Bot, chat_id: int, user_id: int, track: TrackInfo,
                  status: Message | None = None, source_url: str | None = None) -> Message | None:
    """send_track + xatolarni foydalanuvchiga tushunarli qilib ko'rsatish."""
    try:
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VOICE)
        msg = await send_track(bot, chat_id, user_id, track, source_url)
    except DownloadError as e:
        log.error("Yuklab bo'lmadi '%s': %s", track.display, e)
        await _fail(bot, chat_id, status, f"❌ <b>{utils.truncate(track.display, 80)}</b> yuklab bo'lmadi.\n"
                                           "Boshqa variantni tanlab ko'ring.")
        return None
    except TelegramForbiddenError:
        return None
    except Exception:
        log.exception("Kutilmagan xato: %s", track.display)
        await _fail(bot, chat_id, status, "⚠️ Kutilmagan xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return None
    if status:
        try:
            await status.delete()
        except TelegramAPIError:
            pass
    return msg


def new_session(*, tracks: dict[int, TrackInfo] | None = None, yt: dict[int, dict] | None = None) -> str:
    """Qidiruv natijalarini (callback uchun) vaqtincha xotirada saqlaydi."""
    now = time.time()
    for k in [k for k, v in _yt_results.items() if now - v["ts"] > 3600]:
        _yt_results.pop(k, None)
    while len(_yt_results) > 300:
        _yt_results.pop(next(iter(_yt_results)))
    sid = uuid.uuid4().hex[:8]
    _yt_results[sid] = {"ts": now, "tracks": tracks or {}, "items": yt or {}}
    return sid


# =============================================================================
#  Natijalar klaviaturasi
# =============================================================================
def _results_kb(items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i, item in enumerate(items, 1):
        kb.button(text=utils.truncate(f"{i}. {item['label']}", 60), callback_data=item["data"])
    kb.adjust(1)
    return kb.as_markup()


# =============================================================================
#  Top musiqalar
# =============================================================================
@router.message(F.text == config.BTN_TOP)
async def top_tracks(message: Message):
    rows = await db.top_tracks(10)
    if not rows:
        await message.answer("Hozircha top musiqalar yo'q. Birinchi bo'lib qo'shiq yuklab oling! 🎧")
        return
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=utils.truncate(f"🔥 {_row_name(r)}", 60), callback_data=f"dc:{r['id']}")
    kb.adjust(1)
    await message.answer("🔥 <b>Top musiqalar</b>", reply_markup=kb.as_markup())


# =============================================================================
#  Matn / havola qabul qilish (eng oxirgi umumiy handler)
# =============================================================================
@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot):
    text = message.text.strip()
    parsed = spotifier.parse_url(text)

    if parsed:
        kind, sid = parsed
        if kind == "track":
            await _handle_track_link(message, bot, sid)
        else:
            await _handle_album_link(message, sid)
        return

    if "open.spotify.com" in text or "spotify.link" in text:
        await message.answer("⚠️ Hozircha faqat Spotify <b>trek</b> va <b>albom</b> havolalari qo'llab-quvvatlanadi.")
        return

    await _handle_search(message, text)


async def _handle_track_link(message: Message, bot: Bot, sid: str):
    status = await message.answer("🔎 Havola tahlil qilinmoqda…")
    row = await db.get_track_by_spotify_id(sid)
    if row:  # Spotify'ga murojaat qilmasdan, kesh orqali darhol
        track = TrackInfo(sid, row["artist"], row["title"], row["album"], row["cover_url"],
                          (row["duration"] or 0) * 1000 or None)
    else:
        try:
            track = await spotifier.get_track(sid)
        except SpotifyError:
            await status.edit_text("❌ Spotify'dan ma'lumot olib bo'lmadi. Havolani tekshiring yoki qo'shiq nomini yozing.")
            return
    await status.edit_text(f"⏳ <b>{utils.truncate(track.display, 80)}</b> tayyorlanmoqda…")
    await deliver(bot, message.chat.id, message.from_user.id, track, status)


async def _handle_album_link(message: Message, sid: str):
    try:
        album = await spotifier.get_album(sid)
    except SpotifyError:
        await message.answer("❌ Albom ma'lumotini olib bo'lmadi.")
        return
    if not album.tracks:
        await message.answer("Albomda treklar topilmadi.")
        return
    kb = InlineKeyboardBuilder()
    for i, t in enumerate(album.tracks[:20], 1):
        kb.button(text=utils.truncate(f"{i}. {t.title}", 60), callback_data=f"dl:{t.spotify_id}")
    n = min(len(album.tracks), config.ALBUM_MAX_TRACKS)
    kb.button(text=f"📥 Birinchi {n} ta trekni yuklash", callback_data=f"alb:{sid}")
    kb.adjust(1)
    caption = f"💿 <b>{album.name}</b>\n👤 {album.artist}\n🎵 Treklar: {len(album.tracks)}"
    if album.cover_url:
        try:
            await message.answer_photo(album.cover_url, caption=caption, reply_markup=kb.as_markup())
            return
        except TelegramAPIError:
            pass
    await message.answer(caption, reply_markup=kb.as_markup())


async def _handle_search(message: Message, text: str):
    status = await message.answer("🔎 Qidirilmoqda…")

    cached = await db.search_tracks(text, 5)           # 1) bazadagi tayyor treklar
    try:
        found = await spotifier.search(text, TOTAL_RESULTS)   # 2) Spotify
    except SpotifyError:
        found = []

    items: list[dict] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for r in cached:
        items.append({"label": f"⚡ {_row_name(r)}", "data": f"dc:{r['id']}"})
        if r["spotify_id"]:
            seen_ids.add(r["spotify_id"])
        seen_keys.add(r["cache_key"])
    for t in found:
        if len(items) >= TOTAL_RESULTS:
            break
        if t.spotify_id in seen_ids or t.cache_key in seen_keys:
            continue
        seen_ids.add(t.spotify_id)
        seen_keys.add(t.cache_key)
        dur = utils.fmt_duration(t.duration_s)
        items.append({"label": f"🎵 {t.display}" + (f" ({dur})" if dur else ""), "data": f"dl:{t.spotify_id}"})

    # 3) Spotify yetmasa/ishlamasa — Deezer (haqiqiy qo'shiqlar ro'yxati, muqova bilan)
    track_map: dict[int, TrackInfo] = {}
    sid = None
    if len(items) < TOTAL_RESULTS:
        for t in await deezer.search(text, TOTAL_RESULTS + 5):
            if len(items) >= TOTAL_RESULTS:
                break
            if t.cache_key in seen_keys:
                continue
            seen_keys.add(t.cache_key)
            idx = len(track_map)
            track_map[idx] = t
            dur = utils.fmt_duration(t.duration_s)
            items.append({"label": f"🎵 {t.display}" + (f" ({dur})" if dur else ""), "data": f"tk:@SID@:{idx}"})

    # 4) Oxirgi chora — YouTube/SoundCloud natijalari (faqat deyarli hech narsa topilmasa)
    yt_map: dict[int, dict] = {}
    if len(items) < 3:
        try:
            cands = await downloader.search_candidates(text, TOTAL_RESULTS - len(items) + 6)
        except Exception as e:
            log.warning("Zaxira qidiruv xatosi: %s", e)
            cands = []
        seen_titles: set[str] = set()
        for c in cands:
            if len(items) >= TOTAL_RESULTS:
                break
            key = utils.normalize_key(c["title"])
            if key in seen_titles or key in seen_keys:
                continue
            seen_titles.add(key)
            idx = len(yt_map)
            yt_map[idx] = c
            dur = utils.fmt_duration(c["duration"])
            icon = "▶️" if c["source"] == "youtube" else "☁️"
            items.append({"label": f"{icon} {c['title']}" + (f" ({dur})" if dur else ""),
                          "data": f"yt:@SID@:{idx}"})

    if track_map or yt_map:
        sid = new_session(tracks=track_map, yt=yt_map)
        for it in items:
            it["data"] = it["data"].replace("@SID@", sid)

    if not items:
        await status.edit_text(f"⏳ <b>{utils.truncate(text, 80)}</b> to'g'ridan-to'g'ri qidirilmoqda…")
        await deliver(message.bot, message.chat.id, message.from_user.id, TrackInfo(None, "", text), status)
        return

    await status.edit_text(
        f"🔎 <b>«{utils.truncate(text, 60)}»</b> bo'yicha natijalar:\n"
        "<i>⚡ — tayyor (darhol yuboriladi)</i>",
        reply_markup=_results_kb(items),
    )


# =============================================================================
#  Callback'lar
# =============================================================================
@router.callback_query(F.data.startswith("yt:"))
async def cb_youtube(call: CallbackQuery, bot: Bot):
    """Ro'yxatdagi variant tanlandi -> aynan o'sha variant yuklanadi va yuboriladi."""
    _, sid, idx = call.data.split(":")
    cand = (_yt_results.get(sid) or {}).get("items", {}).get(int(idx))
    if not cand:
        await call.answer("Natijalar eskirgan, qayta qidiring.", show_alert=True)
        return
    await call.answer("⏳ Yuklanmoqda…")
    chat_id = call.message.chat.id if call.message else call.from_user.id
    track = TrackInfo(None, "", cand["title"], duration_ms=(cand["duration"] or 0) * 1000 or None)
    status = await bot.send_message(chat_id, f"⏳ <b>{utils.truncate(track.title, 80)}</b> tayyorlanmoqda…")
    await deliver(bot, chat_id, call.from_user.id, track, status, source_url=cand["url"])


@router.callback_query(F.data.startswith("tk:"))
async def cb_track(call: CallbackQuery, bot: Bot):
    """Deezer ro'yxatidan tanlangan qo'shiq: Artist - Title bo'yicha yuklanadi."""
    _, sid, idx = call.data.split(":")
    track = (_yt_results.get(sid) or {}).get("tracks", {}).get(int(idx))
    if not track:
        await call.answer("Natijalar eskirgan, qayta qidiring.", show_alert=True)
        return
    if call.inline_message_id:
        row = await db.find_cached(None, track.cache_key)
        await _inline_flow(call, bot, row=row, spotify_id=None, track=track)
        return
    await call.answer("⏳ Yuklanmoqda…")
    chat_id = call.message.chat.id if call.message else call.from_user.id
    status = await bot.send_message(chat_id, f"⏳ <b>{utils.truncate(track.display, 80)}</b> tayyorlanmoqda…")
    await deliver(bot, chat_id, call.from_user.id, track, status)


async def _edit_inline_audio(bot: Bot, inline_id: str, file_id: str) -> None:
    """Inline xabarni audio bilan almashtiradi (faqat file_id orqali mumkin)."""
    try:
        await bot.edit_message_media(
            media=InputMediaAudio(media=file_id, caption=await utils.bot_caption(bot)),
            inline_message_id=inline_id,
        )
    except TelegramAPIError as e:
        log.warning("Inline xabarni audioga almashtirib bo'lmadi: %s", e)
        try:
            await bot.edit_message_text("✅ Audio tayyor. Uni bot bilan shaxsiy chatda ko'rishingiz mumkin.",
                                        inline_message_id=inline_id)
        except TelegramAPIError:
            pass


async def _inline_flow(call: CallbackQuery, bot: Bot, *, row: dict | None, spotify_id: str | None,
                       track: TrackInfo | None = None) -> None:
    user_id = call.from_user.id
    inline_id = call.inline_message_id
    await call.answer("⏳ Tayyorlanmoqda, biroz kuting…")

    if row:
        file_id = row["file_id"]
        await db.register_download(user_id, row["id"])
    else:
        try:
            track = track or await spotifier.get_track(spotify_id)
            # Inline'da fayl yuklab bo'lmaydi: avval foydalanuvchi PM'iga yuklab, file_id olamiz
            msg = await send_track(bot, user_id, user_id, track)
        except TelegramForbiddenError:
            me = await bot.me()
            await bot.edit_message_text(f"⚠️ Avval @{me.username} botiga o'tib /start bosing, so'ng qayta urinib ko'ring.",
                                        inline_message_id=inline_id)
            return
        except (DownloadError, SpotifyError):
            await bot.edit_message_text("❌ Yuklab bo'lmadi. Keyinroq urinib ko'ring.", inline_message_id=inline_id)
            return
        file_id = msg.audio.file_id
        try:
            await msg.delete()  # vaqtinchalik xabar
        except TelegramAPIError:
            pass
    await _edit_inline_audio(bot, inline_id, file_id)


@router.callback_query(F.data.startswith("dl:"))
async def cb_download(call: CallbackQuery, bot: Bot):
    sid = call.data[3:]
    if call.inline_message_id:
        await _inline_flow(call, bot, row=await db.get_track_by_spotify_id(sid), spotify_id=sid)
        return

    await call.answer("⏳ Yuklanmoqda…")
    chat_id = call.message.chat.id if call.message else call.from_user.id
    row = await db.get_track_by_spotify_id(sid)
    if row and await _send_cached(bot, chat_id, call.from_user.id, row):
        return
    try:
        track = await spotifier.get_track(sid)
    except SpotifyError:
        await bot.send_message(chat_id, "❌ Spotify'dan ma'lumot olib bo'lmadi.")
        return
    status = await bot.send_message(chat_id, f"⏳ <b>{utils.truncate(track.display, 80)}</b> tayyorlanmoqda…")
    await deliver(bot, chat_id, call.from_user.id, track, status)


@router.callback_query(F.data.startswith("dc:"))
async def cb_cached(call: CallbackQuery, bot: Bot):
    row = await db.get_track_by_id(int(call.data[3:]))
    if not row:
        await call.answer("Trek topilmadi.", show_alert=True)
        return
    if call.inline_message_id:
        await _inline_flow(call, bot, row=row, spotify_id=row["spotify_id"])
        return
    await call.answer("⚡ Yuborilmoqda…")
    chat_id = call.message.chat.id if call.message else call.from_user.id
    if not await _send_cached(bot, chat_id, call.from_user.id, row):
        await bot.send_message(chat_id, "⚠️ Bu trek keshdan o'chib ketgan, nomini qayta yozib qidiring.")


@router.callback_query(F.data.startswith("alb:"))
async def cb_album(call: CallbackQuery, bot: Bot):
    uid = call.from_user.id
    if uid in _album_busy:
        await call.answer("Oldingi albom hali yuklanmoqda…", show_alert=True)
        return
    try:
        album = await spotifier.get_album(call.data[4:])
    except SpotifyError:
        await call.answer("Albomni olib bo'lmadi.", show_alert=True)
        return
    await call.answer("📥 Albom yuklanmoqda…")
    chat_id = call.message.chat.id if call.message else uid
    tracks = album.tracks[: config.ALBUM_MAX_TRACKS]
    _album_busy.add(uid)
    try:
        status = await bot.send_message(chat_id, f"📥 Albom yuklanmoqda: 0/{len(tracks)}")
        for i, t in enumerate(tracks, 1):
            await deliver(bot, chat_id, uid, t)
            try:
                await status.edit_text(f"📥 Albom yuklanmoqda: {i}/{len(tracks)}")
            except TelegramAPIError:
                pass
        await status.edit_text(f"✅ <b>{album.name}</b> — tayyor!")
    finally:
        _album_busy.discard(uid)
