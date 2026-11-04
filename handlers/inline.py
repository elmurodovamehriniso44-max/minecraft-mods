import html
import logging

from aiogram import Bot, F, Router
from aiogram.types import (
    ChosenInlineResult,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedAudio,
    InputMediaAudio,
    InputTextMessageContent,
)

import config
from services import downloader, music
from services.db import db

log = logging.getLogger(__name__)
router = Router()

WAIT_KB = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="⏳ Yuklanmoqda...", callback_data="noop")]]
)


@router.inline_query()
async def on_inline(q: InlineQuery):
    text = q.query.strip()[:100]
    if len(text) < 2:
        await q.answer([], cache_time=1, is_personal=True)
        return
    try:
        found = await downloader.search(text, 10)
    except Exception:
        log.exception("Inline qidiruv xatosi")
        await q.answer([], cache_time=1)
        return

    results = []
    for r in found:
        vid = r["id"]
        cached = await db.get_track(f"yt:{vid}")
        if cached:
            # Keshda bor: darhol audio sifatida yuboriladi
            results.append(InlineQueryResultCachedAudio(id=f"c:{vid}", audio_file_id=cached["file_id"]))
        else:
            results.append(
                InlineQueryResultArticle(
                    id=f"y:{vid}",
                    title=r["title"][:100],
                    description=f"{r['uploader']} • {music.fmt_duration(r['duration'])}"[:100],
                    thumbnail_url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    input_message_content=InputTextMessageContent(
                        message_text=f"⏳ <b>{html.escape(r['title'])}</b>\nYuklanmoqda..."
                    ),
                    reply_markup=WAIT_KB,
                )
            )
    await q.answer(results, cache_time=5, is_personal=False)


@router.chosen_inline_result(F.result_id.startswith("y:"))
async def on_chosen(chosen: ChosenInlineResult, bot: Bot):
    """Foydalanuvchi natijani tanladi: yuklab, inline xabarni audioga almashtiramiz.
    BotFather'da /setinlinefeedback ni 100% qiling!"""
    imid = chosen.inline_message_id
    if not imid:
        return
    vid = chosen.result_id[2:]
    if not config.STORAGE_CHAT_ID:
        await bot.edit_message_text("❌ Inline yuklash sozlanmagan (STORAGE_CHAT_ID).", inline_message_id=imid)
        return
    try:
        # Inline xabarga yangi fayl yuklab bo'lmaydi, shuning uchun avval "ombor" chatga
        # yuklab file_id olamiz, keyin xabarni shu file_id bilan almashtiramiz.
        fid, _ = await music.ensure_youtube_cached(bot, vid, config.STORAGE_CHAT_ID)
        tr = await db.get_track(f"yt:{vid}")
        await bot.edit_message_media(
            media=InputMediaAudio(media=fid, title=tr["title"], performer=tr["artist"]),
            inline_message_id=imid,
        )
    except Exception as e:
        log.warning("Inline yuklash xatosi (%s): %s", vid, e)
        try:
            await bot.edit_message_text("❌ Qo'shiqni yuklab bo'lmadi.", inline_message_id=imid)
        except Exception:
            pass
