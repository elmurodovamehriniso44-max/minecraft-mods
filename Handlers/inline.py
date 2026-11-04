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
from services import catalog, music, utils
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
        items = (await catalog.search(text, 12))[:12]
    except Exception:
        log.exception("Inline qidiruv xatosi")
        await q.answer([], cache_time=1)
        return

    results = []
    for it in items:
        cached = await db.get_track(it.key)
        if cached:
            results.append(InlineQueryResultCachedAudio(id=f"c:{it.cb}", audio_file_id=cached["file_id"]))
            continue
        title = it.title or "Qo'shiq"
        results.append(
            InlineQueryResultArticle(
                id=it.cb,
                title=title[:100],
                description=f"{it.artist} • {utils.fmt_duration(it.duration)}"[:100],
                thumbnail_url=it.cover or f"https://i.ytimg.com/vi/{it.id}/hqdefault.jpg",
                input_message_content=InputTextMessageContent(
                    message_text=f"⏳ <b>{html.escape(title)}</b>\nYuklanmoqda..."
                ),
                reply_markup=WAIT_KB,
            )
        )
    await q.answer(results, cache_time=5, is_personal=False)


@router.chosen_inline_result(F.result_id.regexp(r"^[dy]:[\w\-]+$"))
async def on_chosen(chosen: ChosenInlineResult, bot: Bot):
    """BotFather'da /setinlinefeedback ni 100% qiling."""
    imid = chosen.inline_message_id
    if not imid:
        return
    kind, _, ident = chosen.result_id.partition(":")
    if not config.STORAGE_CHAT_ID:
        await bot.edit_message_text("❌ Inline yuklash sozlanmagan (STORAGE_CHAT_ID).", inline_message_id=imid)
        return
    try:
        item = await catalog.resolve(kind, ident)
        fid, _, _ = await music.get_file_id(bot, item, config.STORAGE_CHAT_ID)
        tr = await db.get_track(item.key)
        media = InputMediaAudio(media=fid, title=(tr or {}).get("title") or item.title, performer=(tr or {}).get("artist") or item.artist)
        await bot.edit_message_media(media=media, inline_message_id=imid)
    except Exception as e:
        log.warning("Inline yuklash xatosi (%s): %s", chosen.result_id, e)
        try:
            await bot.edit_message_text("❌ Qo'shiqni yuklab bo'lmadi.", inline_message_id=imid)
        except Exception:
            pass
