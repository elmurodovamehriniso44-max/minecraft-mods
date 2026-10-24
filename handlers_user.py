from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

import db
import keyboards as kb
from texts import GUIDE, GUIDE_INTRO, WELCOME, card_caption, esc, guide_text

router = Router()


class SearchState(StatesGroup):
    waiting = State()


# ---------- Yordamchi funksiyalar ----------
async def show_text(c: CallbackQuery, text: str, markup):
    """Xabarni tahrirlaydi; agar u matn bo'lmasa (rasm/fayl) — o'chirib, yangisini yuboradi."""
    msg = c.message
    if msg.text:
        try:
            await msg.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass
    else:
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        await msg.answer(text, reply_markup=markup)


async def show_card(c: CallbackQuery, mod, markup):
    """Kartani edit_message_media orqali almashtiradi (chat tartibsiz bo'lmasligi uchun)."""
    msg = c.message
    caption = card_caption(mod)
    if msg.photo:
        try:
            await msg.edit_media(
                media=InputMediaPhoto(media=mod.cover, caption=caption), reply_markup=markup
            )
        except TelegramBadRequest:
            pass
    else:
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        await msg.answer_photo(photo=mod.cover, caption=caption, reply_markup=markup)


async def open_card(c: CallbackQuery, cat: str, ver: str, idx: int):
    mod, total, idx = await db.get_mod_at(cat, ver, idx)
    if not mod:
        await c.answer("Hozircha hech narsa yo'q", show_alert=True)
        return
    await show_card(c, mod, kb.card_kb(mod, nav=(cat, ver, idx, total)))
    await c.answer()


# ---------- Boshlash va menyu ----------
@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await db.upsert_user(m.from_user)
    await m.answer(WELCOME, reply_markup=kb.main_menu())


@router.message(Command("menu", "help"))
async def cmd_menu(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(WELCOME, reply_markup=kb.main_menu())


@router.callback_query(F.data == "home")
async def cb_home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_text(c, WELCOME, kb.main_menu())
    await c.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(c: CallbackQuery):
    await c.answer()


@router.callback_query(F.data == "close")
async def cb_close(c: CallbackQuery):
    try:
        await c.message.delete()
    except TelegramBadRequest:
        pass
    await c.answer()


# ---------- Katalog ----------
@router.callback_query(F.data == "catalog")
async def cb_catalog(c: CallbackQuery):
    await show_text(c, "📂 <b>Bo'limni tanlang:</b>", kb.categories())
    await c.answer()


@router.callback_query(F.data.startswith("cat:"))
async def cb_category(c: CallbackQuery):
    cat = c.data.split(":", 1)[1]
    versions = await db.list_versions(cat)
    if not versions:
        await c.answer("Bu bo'limda hozircha fayl yo'q 😔", show_alert=True)
        return
    await show_text(c, "🎮 <b>Minecraft versiyasini tanlang:</b>", kb.versions(cat, versions))
    await c.answer()


@router.callback_query(F.data.startswith("v:"))
async def cb_version(c: CallbackQuery):
    _, cat, ver = c.data.split(":", 2)
    await open_card(c, cat, ver, 0)


@router.callback_query(F.data.startswith("n:"))
async def cb_nav(c: CallbackQuery):
    _, cat, ver, idx = c.data.split(":", 3)
    await open_card(c, cat, ver, int(idx))


@router.callback_query(F.data.startswith("m:"))
async def cb_single(c: CallbackQuery):
    mod = await db.get_mod(int(c.data.split(":")[1]))
    if not mod:
        await c.answer("Topilmadi", show_alert=True)
        return
    await show_card(c, mod, kb.card_kb(mod))
    await c.answer()


# ---------- Yuklab olish va skrinshotlar ----------
@router.callback_query(F.data.startswith("dl:"))
async def cb_download(c: CallbackQuery):
    mod = await db.get_mod(int(c.data.split(":")[1]))
    if not mod:
        await c.answer("Fayl topilmadi", show_alert=True)
        return
    await c.message.answer_document(
        document=mod.file_id,
        caption=(
            f"✅ <b>{esc(mod.title)}</b>\n🎮 Versiya: {esc(mod.version)}\n\n"
            "Faylni bosing — Minecraft o'zi ochiladi. Yordam kerak bo'lsa, pastdagi tugmani bosing 👇"
        ),
        reply_markup=kb.after_download(),
    )
    await db.inc_downloads(mod.id)
    await c.answer("📥 Yuborildi!")


@router.callback_query(F.data.startswith("ss:"))
async def cb_screens(c: CallbackQuery):
    mod = await db.get_mod(int(c.data.split(":")[1]))
    photos = mod.photo_list[1:10] if mod else []
    if not photos:
        await c.answer("Qo'shimcha rasm yo'q", show_alert=True)
        return
    if len(photos) == 1:
        await c.message.answer_photo(photos[0])
    else:
        await c.message.answer_media_group([InputMediaPhoto(media=p) for p in photos])
    await c.answer()


# ---------- Yo'riqnoma ----------
@router.callback_query(F.data == "guide")
async def cb_guide(c: CallbackQuery):
    await c.message.answer(GUIDE_INTRO, reply_markup=kb.guide_os())
    await c.answer()


@router.callback_query(F.data.startswith("g:"))
async def cb_guide_os(c: CallbackQuery):
    key = c.data.split(":")[1]
    if key not in GUIDE:
        await c.answer()
        return
    try:
        await c.message.edit_text(guide_text(key), reply_markup=kb.guide_os(), disable_web_page_preview=True)
    except TelegramBadRequest:
        pass
    await c.answer()


# ---------- Qidirish ----------
@router.callback_query(F.data == "search")
async def cb_search(c: CallbackQuery, state: FSMContext):
    await state.set_state(SearchState.waiting)
    await c.message.answer("🔍 Kalit so'z yozing (masalan: <i>furniture</i>, <i>gun</i>, <i>one block</i>):")
    await c.answer()


@router.message(StateFilter(SearchState.waiting, None), F.text, ~F.text.startswith("/"), F.chat.type == "private")
async def do_search(m: Message, state: FSMContext):
    await state.clear()
    query = m.text.strip()[:60]
    mods = await db.search_mods(query)
    if not mods:
        await m.answer(
            f"😕 «{esc(query)}» bo'yicha hech narsa topilmadi.\nBoshqa so'z bilan urinib ko'ring.",
            reply_markup=kb.main_menu(),
        )
        return
    await m.answer(
        f"🔍 «{esc(query)}» bo'yicha <b>{len(mods)}</b> ta natija:", reply_markup=kb.search_results(mods)
    )
