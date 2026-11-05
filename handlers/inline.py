"""Inline rejim: @bot_username qo'shiq nomi"""
import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultArticle,
    InlineQueryResultCachedAudio, InputTextMessageContent,
)

from services import db, deezer, spotifier, utils
from services.spotifier import SpotifyError

from . import music as music_handlers

log = logging.getLogger(__name__)
router = Router(name="inline")


def _article(rid: str, title: str, desc: str, callback_data: str, thumb: str | None = None):
    safe = utils.truncate(title, 100)
    return InlineQueryResultArticle(
        id=rid[:64],
        title=safe,
        description=desc,
        thumbnail_url=thumb,
        input_message_content=InputTextMessageContent(
            message_text=f"🎵 <b>{safe}</b>\n\n<i>Audio yuklash uchun tugmani bosing 👇</i>",
            parse_mode="HTML",
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬇️ Yuklab olish", callback_data=callback_data)
        ]]),
    )


@router.inline_query()
async def on_inline(query: InlineQuery, bot: Bot):
    text = (query.query or "").strip()

    # Bo'sh so'rov: eng ko'p yuklangan tayyor musiqalar (darhol yuboriladi)
    if len(text) < 2:
        rows = await db.top_tracks(20)
        if rows:
            caption = await utils.bot_caption(bot)
            results = [InlineQueryResultCachedAudio(id=f"c{r['id']}", audio_file_id=r["file_id"], caption=caption)
                       for r in rows]
        else:
            results = [InlineQueryResultArticle(
                id="hint", title="Qo'shiq nomini yozing…", description="Masalan: Imagine Dragons Believer",
                input_message_content=InputTextMessageContent(message_text="🎧 Qo'shiq nomini yozing."),
            )]
        await _safe_answer(query, results, cache_time=30)
        return

    cached = await db.search_tracks(text, 8)
    try:
        found = await spotifier.search(text, 8)
    except SpotifyError:
        found = []

    results = []
    seen_ids = {r["spotify_id"] for r in cached if r["spotify_id"]}
    seen_keys = {r["cache_key"] for r in cached}
    for r in cached:
        name = f"{r['artist']} — {r['title']}" if r["artist"] else r["title"]
        cb = f"dl:{r['spotify_id']}" if r["spotify_id"] else f"dc:{r['id']}"
        results.append(_article(f"c{r['id']}", f"⚡ {name}", "Tayyor — tezda yuboriladi", cb, r["cover_url"]))
    for t in found:
        if t.spotify_id in seen_ids or t.cache_key in seen_keys:
            continue
        seen_keys.add(t.cache_key)
        desc = " • ".join(x for x in (t.album, utils.fmt_duration(t.duration_s)) if x)
        results.append(_article(f"s{t.spotify_id}", t.display, desc, f"dl:{t.spotify_id}", t.cover_url))

    # Spotify yetmasa/ishlamasa — Deezer ro'yxati
    if len(results) < 10:
        extra = [t for t in await deezer.search(text, 15) if t.cache_key not in seen_keys]
        extra = extra[: 10 - len(results)]
        if extra:
            sid = music_handlers.new_session(tracks=dict(enumerate(extra)))
            for i, t in enumerate(extra):
                desc = " • ".join(x for x in (t.album, utils.fmt_duration(t.duration_s)) if x)
                results.append(_article(f"d{sid}{i}", t.display, desc, f"tk:{sid}:{i}", t.cover_url))

    if not results:
        results = [InlineQueryResultArticle(
            id="none", title="Hech narsa topilmadi", description="Boshqa nom bilan urinib ko'ring",
            input_message_content=InputTextMessageContent(message_text="❌ Hech narsa topilmadi."),
        )]
    await _safe_answer(query, results, cache_time=20)


async def _safe_answer(query: InlineQuery, results: list, cache_time: int) -> None:
    try:
        await query.answer(results[:50], cache_time=cache_time, is_personal=False)
    except TelegramAPIError as e:
        log.warning("Inline javob xatosi: %s", e)
