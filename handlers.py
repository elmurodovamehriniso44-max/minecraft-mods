"""aiogram 3.x handlerlari."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from aiogram import F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from modrinth_service import ModrinthAPIError, ModrinthPEService

logger = logging.getLogger(__name__)
router = Router(name="main")

PROJECT_CB_PREFIX = "pe:"
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")
_MD_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")

TYPE_EMOJI = {
    "modpack": "📦",
    "resourcepack": "🎨",
    "mod": "🧩",
    "shader": "✨",
    "datapack": "🗂",
}


class SearchStates(StatesGroup):
    waiting_query = State()


def md(text: str) -> str:
    """MarkdownV2 uchun matnni xavfsiz qochirish."""
    return _MD_SPECIAL.sub(r"\\\1", text)


def md_url(url: str) -> str:
    return url.replace("\\", "\\\\").replace(")", "\\)")


def shorten(text: str, length: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


# ------------------------------------------------------------------- /start
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, redis: Any) -> None:
    user = message.from_user
    if user is not None:
        try:
            await redis.sadd("bot:users", user.id)
            await redis.hset(
                f"bot:user:{user.id}",
                mapping={
                    "username": user.username or "",
                    "first_name": user.first_name or "",
                    "language": user.language_code or "",
                    "last_seen": int(time.time()),
                },
            )
        except Exception:
            logger.warning("Foydalanuvchini Redis'ga yozib bo'lmadi", exc_info=True)

    await state.clear()
    await state.set_state(SearchStates.waiting_query)

    name = md(user.first_name) if user else "do'st"
    await message.answer(
        f"👋 Salom, *{name}*\\!\n\n"
        "Men *Minecraft PE \\(Bedrock\\)* uchun addon, mod, resurs to'plami va "
        "xaritalarni topib beraman\\.\n\n"
        "🔎 Qidirish uchun mod yoki addon nomini yozing\\.\n"
        "_Masalan: furniture, dragon, shaders_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ------------------------------------------------------------------- qidiruv
@router.message(F.text & ~F.text.startswith("/"))
async def handle_search(
    message: Message,
    state: FSMContext,
    service: ModrinthPEService,
    search_limit: int,
) -> None:
    query = " ".join((message.text or "").split())
    if len(query) < 2:
        await message.answer("✍️ Iltimos, kamida 2 ta belgidan iborat nom yozing.")
        return

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        results = await service.search_pe_content(query, limit=search_limit)
    except ModrinthAPIError:
        logger.exception("Qidiruv xatosi: %r", query)
        await message.answer(
            "⚠️ Modrinth serveri hozir javob bermayapti. Birozdan so'ng qayta urinib ko'ring."
        )
        return

    await state.set_state(SearchStates.waiting_query)
    await state.update_data(last_query=query)

    if not results:
        await message.answer(
            f"😕 «{shorten(query, 40)}» bo'yicha PE kontenti topilmadi.\n"
            "Boshqa nom yoki inglizcha kalit so'z bilan urinib ko'ring."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{TYPE_EMOJI.get(item['project_type'], '🧩')} {shorten(item['name'], 45)}",
                    callback_data=f"{PROJECT_CB_PREFIX}{item['id']}",
                )
            ]
            for item in results
        ]
    )
    await message.answer(
        f"✅ *{len(results)}* ta natija topildi\\. Kerakligini tanlang:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ------------------------------------------------------- element tafsilotlari
@router.callback_query(F.data.startswith(PROJECT_CB_PREFIX))
async def handle_project(callback: CallbackQuery, service: ModrinthPEService) -> None:
    project_id = (callback.data or "")[len(PROJECT_CB_PREFIX):]
    if not _PROJECT_ID_RE.match(project_id):
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    await callback.answer("⏳ Yuklanmoqda...")
    if not isinstance(callback.message, Message):
        return
    chat_id = callback.message.chat.id
    await callback.bot.send_chat_action(chat_id, ChatAction.TYPING)

    try:
        info = await service.get_latest_pe_download(project_id)
    except ModrinthAPIError:
        logger.exception("Yuklash ma'lumotini olishda xato: %s", project_id)
        await callback.message.answer(
            "⚠️ Ma'lumotni olib bo'lmadi\\. Birozdan so'ng qayta urinib ko'ring\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if not info:
        await callback.message.answer(
            "😕 Bu loyiha uchun mobil (Bedrock) formatidagi fayl "
            "(.mcaddon / .mcpack / .mcworld / .zip) topilmadi."
        )
        return

    size = f"{info['size_mb']:.2f} MB" if info["size_mb"] else "noma'lum"
    description = shorten(info["description"], 500) or "Tavsif mavjud emas."
    ext = info["extension"]
    link_label = f"📥 {ext} faylini yuklab olish"
    safe_filename = info["filename"].replace("\\", "\\\\").replace("`", "\\`")

    text = (
        f"*{md(info['name'])}*\n\n"
        f"{md(description)}\n\n"
        f"📦 *Hajmi:* {md(size)}\n"
        f"🏷 *Versiya:* {md(str(info['version']))}\n"
        f"📄 *Fayl:* `{safe_filename}`\n\n"
        f"[{md(link_label)}]({md_url(info['url'])})"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=link_label, url=info["url"])],
            [InlineKeyboardButton(text="🌐 Modrinth sahifasi", url=info["project_url"])],
        ]
    )
    await callback.message.answer(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
