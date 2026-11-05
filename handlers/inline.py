import html
import logging

from aiogram import Bot, Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedAudio,
    InputTextMessageContent,
)

from services import db, downloader, utils

logger = logging.getLogger(__name__)
router = Router()


def _article(rid: str, title: str, text: str, url: str | None = None) -> InlineQueryResultArticle:
    markup = None
    if url:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="▶️ Tinglash", url=url)]])
    return InlineQueryResultArticle(
        id=rid[:64],
        title=title,
        input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
        reply_markup=markup,
    )


@router.inline_query()
async def on_inline(q: InlineQuery, bot: Bot) -> None:
    try:
        query = (q.query or "").strip()
        if len(query) < 2:
            await q.answer([], cache_time=5, is_personal=True)
            return

        me = await bot.me()
        if not await utils.is_subscribed(bot, q.from_user.id):
            await q.answer(
                [_article("sub", "📢 Avval kanalga obuna bo'ling", f"Botdan foydalanish uchun @{me.username} ga o'tib kanalga obuna bo'ling.")],
                cache_time=5,
                is_personal=True,
            )
            return

        cached = await db.search_tracks(query, limit=8)
        try:
            yt = await downloader.search_youtube(query, limit=10)
        except Exception as e:
            logger.warning("Inline qidiruv (YouTube) xatosi: %s", str(e)[:200])
            yt = []
        have = await db.get_tracks([r.video_id for r in yt])

        answers, seen = [], set()
        for r in cached:  # bazada bor -> guruhning o'zida darhol audio yuboriladi
            seen.add(r["file_id"])
            answers.append(InlineQueryResultCachedAudio(id=r["key"][:64], audio_file_id=r["file_id"]))
        for r in yt:  # yo'q -> botga deep-link orqali o'tadi
            row = have.get(r.video_id)
            if row and row["file_id"] in seen:
                continue
            if row:
                seen.add(row["file_id"])
                answers.append(InlineQueryResultCachedAudio(id=r.video_id, audio_file_id=row["file_id"]))
                continue
            label = f"{r.artist} - {r.title}"
            answers.append(
                _article(
                    r.video_id,
                    f"🎵 {label}",
                    f"🎵 <b>{html.escape(label)}</b>\n\nTinglash uchun tugmani bosing 👇",
                    f"https://t.me/{me.username}?start=dl_{r.video_id}",
                )
            )
        await q.answer(answers[:50], cache_time=60)
    except Exception:
        logger.exception("Inline qidiruvda xatolik")
        try:
            await q.answer([], cache_time=5)
        except Exception:
            pass
