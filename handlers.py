"""aiogram 3.x handlerlari."""
from __future__ import annotations

import html
import logging
from typing import Any, Dict, List

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from modrinth_service import ModrinthError, ModrinthPEService

logger = logging.getLogger(__name__)
router = Router(name="main")

DETAIL_PREFIX = "pe:"


class SearchStates(StatesGroup):
    browsing = State()


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _results_keyboard(results: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in results:
        label = f"🧩 {_truncate(item['title'], 55)}"
        builder.button(text=label, callback_data=f"{DETAIL_PREFIX}{item['id']}")
    builder.adjust(1)
    return builder.as_markup()


# ------------------------------------------------------------------- /start
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SearchStates.browsing)
    name = html.escape(message.from_user.first_name if message.from_user else "do'st")
    await message.answer(
        f"👋 Salom, <b>{name}</b>!\n\n"
        "Bu bot <b>Minecraft PE (Bedrock, mobil)</b> uchun mod, addon, "
        "resurs to'plami va xaritalarni topishga yordam beradi.\n\n"
        "🔎 Qidirish uchun mod yoki addon nomini yozing.\n"
        "Masalan: <code>dragon</code>, <code>furniture</code>, <code>shaders</code>"
    )


# ------------------------------------------------------------------- search
@router.message(F.text, ~F.text.startswith("/"))
async def search_handler(message: Message, state: FSMContext,
                         service: ModrinthPEService) -> None:
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("✍️ Iltimos, kamida 2 ta belgidan iborat nom yozing.")
        return
    if len(query) > 80:
        query = query[:80]

    status_msg = await message.answer("🔎 Qidirilmoqda...")
    try:
        results = await service.search_pe_content(query, limit=6)
    except ModrinthError as exc:
        logger.error("Search failed: %s", exc)
        await status_msg.edit_text(
            "⚠️ Qidiruv xizmati vaqtincha ishlamayapti. Birozdan so'ng qayta urinib ko'ring."
        )
        return

    if not results:
        await status_msg.edit_text(
            f"😕 «{html.escape(query)}» bo'yicha PE kontenti topilmadi.\n"
            "Boshqa kalit so'z bilan urinib ko'ring."
        )
        return

    await state.set_state(SearchStates.browsing)
    await state.update_data(
        last_query=query,
        results={r["id"]: r for r in results},
    )
    await status_msg.edit_text(
        f"✅ «<b>{html.escape(query)}</b>» bo'yicha natijalar ({len(results)} ta):\n"
        "Batafsil ko'rish uchun birini tanlang 👇",
        reply_markup=_results_keyboard(results),
    )


# ------------------------------------------------------------------ details
@router.callback_query(F.data.startswith(DETAIL_PREFIX))
async def detail_handler(callback: CallbackQuery, state: FSMContext,
                         service: ModrinthPEService) -> None:
    project_id = (callback.data or "")[len(DETAIL_PREFIX):]
    if not project_id or not isinstance(callback.message, Message):
        await callback.answer("Xatolik yuz berdi.", show_alert=True)
        return
    await callback.answer("⏳ Yuklanmoqda...")

    data = await state.get_data()
    project = (data.get("results") or {}).get(project_id)

    try:
        if project is None:
            project = await service.get_project(project_id)
        download = await service.get_latest_pe_download(project_id)
    except ModrinthError as exc:
        logger.error("Detail failed for %s: %s", project_id, exc)
        await callback.message.answer(
            "⚠️ Ma'lumotni olib bo'lmadi. Birozdan so'ng qayta urinib ko'ring."
        )
        return

    title = html.escape(project["title"])
    description = html.escape(_truncate(project.get("description", ""), 600)) or "Tavsif yo'q."
    lines = [f"🧩 <b>{title}</b>", "", f"📝 {description}", ""]

    builder = InlineKeyboardBuilder()
    if download and download.get("url"):
        filename = download["filename"]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "zip"
        version = download.get("version_number") or download.get("version_name") or "—"
        games = download.get("game_versions") or []
        lines.append(f"📦 Hajmi: <b>{download['size_mb']} MB</b>")
        lines.append(f"🏷 Versiya: <b>{html.escape(str(version))}</b>")
        if games:
            lines.append(f"🎮 O'yin versiyalari: {html.escape(', '.join(games[:5]))}")
        lines.append(f"📄 Fayl: <code>{html.escape(filename)}</code>")
        lines.append("")
        lines.append(
            f'📥 <a href="{html.escape(download["url"], quote=True)}">'
            f".{ext} faylini yuklab olish</a>"
        )
        builder.button(text=f"📥 .{ext} yuklab olish", url=download["url"])
        builder.button(text="🌐 Modrinth sahifasi", url=download["page_url"])
    else:
        lines.append("❌ Bu loyiha uchun yuklab olinadigan fayl topilmadi.")
        builder.button(
            text="🌐 Modrinth sahifasi",
            url=f"https://modrinth.com/project/{project_id}",
        )
    builder.adjust(1)
    markup = builder.as_markup()
    caption = "\n".join(lines)

    icon_url = project.get("icon_url")
    if icon_url and len(caption) <= 1024:
        try:
            await callback.message.answer_photo(icon_url, caption=caption, reply_markup=markup)
            return
        except Exception as exc:  # belgi yuklanmasa matn ko'rinishida yuboramiz
            logger.warning("answer_photo failed: %s", exc)

    await callback.message.answer(caption, reply_markup=markup, disable_web_page_preview=True)
