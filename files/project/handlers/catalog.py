"""Katalog: ro'yxatlar, qidiruv, kategoriyalar, versiyalar, mod kartasi, sevimlilar, yuklab olish."""
import logging
import math

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import queries as q
from keyboards import inline as K
from services import search as search_service
from states.states import SearchState
from utils import texts as T
from utils.filters import PlainText
from utils.helpers import edit_ignore, fit_caption, is_admin, safe_edit

log = logging.getLogger(__name__)
router = Router(name="catalog")


def _pages(total: int) -> int:
    return max(1, math.ceil(total / config.PAGE_SIZE))


# ================================================================== RO'YXATLAR
async def build_list_view(user_id: int, kind: str, arg: int, page: int, state: FSMContext):
    user_version = await q.get_user_version(user_id)
    extra_rows = None

    if kind == "srch":
        data = await state.get_data()
        query = data.get("sq")
        if not query:
            return T.SEARCH_EXPIRED, K.search_retry_kb()
        cat_id = int(data.get("scat") or 0)
        version_on = bool(data.get("sver")) and bool(user_version)
        ids = await search_service.search(
            query, cat_id or None, user_version if version_on else None
        )
        total = len(ids)
        pages = _pages(total)
        page = min(max(page, 0), pages - 1)
        start = page * config.PAGE_SIZE
        rows = await q.get_mods_by_ids(ids[start:start + config.PAGE_SIZE])
        cat_name = None
        if cat_id:
            cat = await q.get_category(cat_id)
            cat_name = cat["name"] if cat else None
        extra_rows = K.search_filter_rows(cat_name, version_on)
        title = T.search_title(query)
    else:
        rows, total, page = await q.list_mods(kind, arg, page, user_id, user_version)
        pages = _pages(total)
        if kind == "cat":
            cat = await q.get_category(arg)
            title = T.category_title(cat["name"], cat["emoji"]) if cat else "📂 <b>Kategoriya</b>"
        elif kind == "ver":
            title = T.version_list_title(user_version or "?")
            if not user_version:
                extra_rows = [[K.btn("🎮 Versiyani tanlash", "vers")]]
        else:
            title = T.LIST_TITLES.get(kind, T.LIST_TITLES["all"])

    text = T.list_text(kind, title, total, page, pages, user_version)
    kb = K.mods_list_kb(rows, kind, arg, page, pages, user_version, extra_rows)
    return text, kb


async def show_list(cb: CallbackQuery, state: FSMContext, kind: str, arg: int, page: int) -> None:
    text, kb = await build_list_view(cb.from_user.id, kind, arg, page, state)
    await safe_edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("lst:"))
async def cb_list(cb: CallbackQuery, state: FSMContext) -> None:
    _, kind, arg, page = cb.data.split(":")
    if kind != "srch":
        await state.set_state(None)  # qidiruv kutish holatidan chiqamiz (ma'lumot saqlanadi)
    await show_list(cb, state, kind, int(arg), int(page))


# ==================================================================== QIDIRUV
@router.callback_query(F.data == "search")
async def cb_search(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchState.query)
    await safe_edit(cb, T.SEARCH_PROMPT, K.menu_only_kb())
    await cb.answer()


@router.message(SearchState.query, PlainText())
async def on_search_query(message: Message, state: FSMContext) -> None:
    query = " ".join(message.text.split())
    if not 2 <= len(query) <= 60:
        await message.answer(T.SEARCH_BAD_LENGTH)
        return
    await state.set_state(None)
    await state.update_data(sq=query, scat=0, sver=False)
    text, kb = await build_list_view(message.from_user.id, "srch", 0, 0, state)
    await message.answer(text, reply_markup=kb)


@router.message(SearchState.query)
async def on_search_wrong_input(message: Message) -> None:
    await message.answer(T.NEED_TEXT)


@router.callback_query(F.data == "sfc")
async def cb_search_pick_category(cb: CallbackQuery) -> None:
    cats = await q.get_categories()
    await safe_edit(cb, T.SEARCH_PICK_CATEGORY, K.search_categories_kb(cats))
    await cb.answer()


@router.callback_query(F.data.startswith("sfc:"))
async def cb_search_set_category(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(scat=int(cb.data.split(":")[1]))
    await show_list(cb, state, "srch", 0, 0)


@router.callback_query(F.data == "sfv")
async def cb_search_toggle_version(cb: CallbackQuery, state: FSMContext) -> None:
    if not await q.get_user_version(cb.from_user.id):
        await cb.answer(T.SEARCH_NEED_VERSION, show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(sver=not data.get("sver", False))
    await show_list(cb, state, "srch", 0, 0)


# ================================================================ KATEGORIYALAR
@router.callback_query(F.data == "cats")
async def cb_categories(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    cats = await q.get_categories_with_counts()
    await safe_edit(cb, T.CATEGORIES_TEXT, K.categories_kb(cats))
    await cb.answer()


# ================================================================== VERSIYALAR
async def _show_versions(cb: CallbackQuery) -> None:
    current = await q.get_user_version(cb.from_user.id)
    await safe_edit(cb, T.versions_text(current), K.versions_kb(current))


@router.callback_query(F.data == "vers")
async def cb_versions(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await _show_versions(cb)
    await cb.answer()


@router.callback_query(F.data.startswith("setv:"))
async def cb_set_version(cb: CallbackQuery) -> None:
    version = cb.data.split(":", 1)[1]
    if version not in config.MC_VERSIONS:
        await cb.answer(T.STALE_BUTTON, show_alert=True)
        return
    await q.set_user_version(cb.from_user.id, version)
    await _show_versions(cb)
    await cb.answer(f"✅ Versiya tanlandi: {version}")


@router.callback_query(F.data == "clrv")
async def cb_clear_version(cb: CallbackQuery) -> None:
    await q.set_user_version(cb.from_user.id, None)
    await _show_versions(cb)
    await cb.answer("🚫 Versiya filtri o'chirildi")


# ================================================================ MOD KARTASI
async def _send_card(cb: CallbackQuery, mod, text: str, kb) -> None:
    """Kartani yuboradi: preview bo'lsa rasm bilan, aks holda matn sifatida."""
    msg = cb.message
    has_preview = bool(mod["preview_file_id"])
    if isinstance(msg, Message):
        if msg.photo and has_preview:
            await edit_ignore(msg.edit_caption(caption=text, reply_markup=kb))
            return
        if msg.text is not None and not has_preview:
            await edit_ignore(msg.edit_text(text, reply_markup=kb))
            return
        try:
            await msg.delete()
        except TelegramAPIError:
            pass
    if has_preview:
        try:
            await cb.bot.send_photo(
                cb.from_user.id, mod["preview_file_id"], caption=text, reply_markup=kb
            )
            return
        except TelegramAPIError as exc:
            log.warning("Preview yuborilmadi (mod %s): %s", mod["id"], exc)
    await cb.bot.send_message(cb.from_user.id, text, reply_markup=kb)


async def show_card(cb: CallbackQuery, mod_id: int, kind: str, arg: int, page: int) -> None:
    mod = await q.get_mod(mod_id)
    if not mod:
        await safe_edit(cb, T.MOD_NOT_FOUND, K.menu_only_kb())
        return
    user_version = await q.get_user_version(cb.from_user.id)
    is_fav = await q.is_favorite(cb.from_user.id, mod_id)
    text = fit_caption(lambda lim: T.mod_card(mod, user_version, lim))
    kb = K.mod_card_kb(mod_id, is_fav, kind, arg, page, is_admin(cb.from_user.id))
    await _send_card(cb, mod, text, kb)


@router.callback_query(F.data.startswith("mod:"))
async def cb_mod(cb: CallbackQuery, state: FSMContext) -> None:
    _, mod_id, kind, arg, page = cb.data.split(":")
    if kind != "srch":
        await state.set_state(None)
    await show_card(cb, int(mod_id), kind, int(arg), int(page))
    await cb.answer()


@router.callback_query(F.data.startswith("ins:"))
async def cb_instructions(cb: CallbackQuery) -> None:
    _, mod_id, kind, arg, page = cb.data.split(":")
    mod = await q.get_mod(int(mod_id))
    if not mod:
        await cb.answer(T.MOD_NOT_FOUND, show_alert=True)
        return
    text = fit_caption(lambda lim: T.instructions_text(mod, lim))
    kb = K.instructions_kb(mod["id"], kind, int(arg), int(page))
    await _send_card(cb, mod, text, kb)
    await cb.answer()


# ================================================================== SEVIMLILAR
@router.callback_query(F.data.startswith("fv:"))
async def cb_favorite(cb: CallbackQuery) -> None:
    _, mod_id, kind, arg, page = cb.data.split(":")
    mod = await q.get_mod(int(mod_id))
    if not mod:
        await cb.answer(T.MOD_NOT_FOUND, show_alert=True)
        return
    now_fav = await q.toggle_favorite(cb.from_user.id, mod["id"])
    await cb.answer("⭐ Sevimlilarga qo'shildi" if now_fav else "💔 Sevimlilardan olib tashlandi")
    await show_card(cb, mod["id"], kind, int(arg), int(page))


# =============================================================== YUKLAB OLISH
@router.callback_query(F.data.startswith("dl:"))
async def cb_download(cb: CallbackQuery) -> None:
    mod = await q.get_mod(int(cb.data.split(":")[1]))
    if not mod:
        await cb.answer(T.MOD_NOT_FOUND, show_alert=True)
        return
    try:
        await cb.bot.send_chat_action(cb.from_user.id, ChatAction.UPLOAD_DOCUMENT)
        caption = fit_caption(lambda lim: T.download_caption(mod, lim))
        await cb.bot.send_document(cb.from_user.id, mod["file_id"], caption=caption)
    except TelegramAPIError as exc:
        log.warning("Fayl yuborilmadi (mod %s): %s", mod["id"], exc)
        await cb.answer(T.FILE_ERROR, show_alert=True)
        return
    await q.record_download(cb.from_user.id, mod["id"])
    await cb.answer(T.FILE_SENT)
