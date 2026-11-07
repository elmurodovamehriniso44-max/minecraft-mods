"""Admin panel: modlarni qo'shish/tahrirlash/o'chirish, statistika, so'rovlar."""
import logging
import math

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import queries as q
from keyboards import admin as AK
from services.files import file_extension, validate_document
from states.states import AddMod, EditMod
from utils import texts as T
from utils.filters import IsAdmin, PlainText
from utils.helpers import join_versions, parse_versions, safe_edit

log = logging.getLogger(__name__)

router = Router(name="admin")
# Barcha admin handlerlari faqat ADMIN_IDS uchun
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

FIELD_LIMITS = {
    "name": (2, 60),
    "description": (1, 500),
    "author": (1, 40),
    "instructions": (0, 500),
}
FIELD_ERRORS = {
    "name": T.ERR_NAME_LEN,
    "description": T.ERR_DESC_LEN,
    "author": T.ERR_AUTHOR_LEN,
    "instructions": T.ERR_INSTR_LEN,
}


def _pages(total: int) -> int:
    return max(1, math.ceil(total / config.PAGE_SIZE))


# ================================================================ ASOSIY PANEL
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(T.ADMIN_HOME, reply_markup=AK.admin_menu_kb())


@router.callback_query(F.data == "adm:home")
async def cb_home(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(cb, T.ADMIN_HOME, AK.admin_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(cb, T.ADMIN_CANCELLED, AK.admin_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_stats(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    stats = await q.get_stats()
    await safe_edit(cb, T.stats_text(stats), AK.panel_back_kb())
    await cb.answer()


# ================================================================ MOD QO'SHISH
@router.callback_query(F.data == "adm:add")
async def add_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddMod.name)
    await safe_edit(cb, T.ADD_NAME, AK.cancel_kb())
    await cb.answer()


@router.message(AddMod.name, PlainText())
async def add_name(message: Message, state: FSMContext) -> None:
    name = " ".join(message.text.split())
    if not 2 <= len(name) <= 60:
        await message.answer(T.ERR_NAME_LEN)
        return
    await state.update_data(name=name)
    await state.set_state(AddMod.description)
    await message.answer(T.ADD_DESC, reply_markup=AK.cancel_kb())


@router.message(AddMod.description, PlainText())
async def add_description(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    if not 1 <= len(desc) <= 500:
        await message.answer(T.ERR_DESC_LEN)
        return
    await state.update_data(description=desc)
    await state.set_state(AddMod.category)
    cats = await q.get_categories()
    await message.answer(
        T.ADD_CATEGORY,
        reply_markup=AK.categories_pick_kb(cats, "adm:acat", "adm:cancel", "❌ Bekor qilish"),
    )


@router.callback_query(AddMod.category, F.data.startswith("adm:acat:"))
async def add_category(cb: CallbackQuery, state: FSMContext) -> None:
    cat = await q.get_category(int(cb.data.split(":")[2]))
    if not cat:
        await cb.answer(T.STALE_BUTTON, show_alert=True)
        return
    await state.update_data(category_id=cat["id"])
    await state.set_state(AddMod.author)
    await safe_edit(cb, T.ADD_AUTHOR, AK.cancel_kb())
    await cb.answer()


@router.message(AddMod.author, PlainText())
async def add_author(message: Message, state: FSMContext) -> None:
    author = " ".join(message.text.split())
    if not 1 <= len(author) <= 40:
        await message.answer(T.ERR_AUTHOR_LEN)
        return
    await state.update_data(author=author, versions=[])
    await state.set_state(AddMod.versions)
    await message.answer(
        T.ADD_VERSIONS,
        reply_markup=AK.versions_toggle_kb(set(), "adm:av", "adm:cancel", "❌ Bekor qilish"),
    )


@router.callback_query(AddMod.versions, F.data.startswith("adm:av:"))
async def add_versions(cb: CallbackQuery, state: FSMContext) -> None:
    action = cb.data.split(":")[2]
    data = await state.get_data()
    selected = set(data.get("versions", []))

    if action == "done":
        await state.set_state(AddMod.preview)
        await safe_edit(cb, T.ADD_PREVIEW, AK.cancel_kb())
        await cb.answer()
        return

    if action not in config.MC_VERSIONS:
        await cb.answer(T.STALE_BUTTON, show_alert=True)
        return
    selected ^= {action}
    await state.update_data(versions=[v for v in config.MC_VERSIONS if v in selected])
    await cb.message.edit_reply_markup(
        reply_markup=AK.versions_toggle_kb(selected, "adm:av", "adm:cancel", "❌ Bekor qilish")
    )
    await cb.answer()


@router.message(AddMod.preview, F.photo)
async def add_preview(message: Message, state: FSMContext) -> None:
    await state.update_data(preview_file_id=message.photo[-1].file_id)
    await state.set_state(AddMod.file)
    await message.answer(T.ADD_FILE, reply_markup=AK.cancel_kb())


@router.message(AddMod.preview)
async def add_preview_wrong(message: Message) -> None:
    await message.answer(T.ERR_NEED_PHOTO)


@router.message(AddMod.file, F.document)
async def add_file(message: Message, state: FSMContext) -> None:
    doc = message.document
    error = validate_document(doc)
    if error:
        await message.answer(error)
        return
    await state.update_data(
        file_id=doc.file_id,
        file_unique_id=doc.file_unique_id,
        file_name=doc.file_name or "mod",
        file_size=doc.file_size or 0,
        file_type=file_extension(doc.file_name),
    )
    await state.set_state(AddMod.instructions)
    await message.answer(T.ADD_INSTRUCTIONS, reply_markup=AK.instructions_skip_kb())


@router.message(AddMod.file)
async def add_file_wrong(message: Message) -> None:
    await message.answer(T.ERR_NEED_DOCUMENT)


async def _save_new_mod(state: FSMContext, instructions: str):
    """Modni bazaga saqlaydi. (mod_id, name) yoki None qaytaradi."""
    data = await state.get_data()
    required = ("name", "description", "category_id", "author", "preview_file_id", "file_id")
    if not all(key in data for key in required):
        await state.clear()
        return None
    mod_id = await q.add_mod(
        name=data["name"],
        description=data["description"],
        category_id=data["category_id"],
        author=data["author"],
        versions=join_versions(data.get("versions", [])),
        preview_file_id=data["preview_file_id"],
        file_id=data["file_id"],
        file_unique_id=data.get("file_unique_id", ""),
        file_name=data.get("file_name", ""),
        file_size=data.get("file_size", 0),
        file_type=data.get("file_type", ""),
        instructions=instructions,
    )
    await state.clear()
    return mod_id, data["name"]


@router.message(AddMod.instructions, PlainText())
async def add_instructions(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) > 500:
        await message.answer(T.ERR_INSTR_LEN)
        return
    result = await _save_new_mod(state, text)
    if result is None:
        await message.answer(T.ADMIN_STATE_LOST, reply_markup=AK.admin_menu_kb())
        return
    mod_id, name = result
    await message.answer(T.mod_added(mod_id, name), reply_markup=AK.after_add_kb(mod_id))


@router.callback_query(AddMod.instructions, F.data == "adm:askip")
async def add_instructions_skip(cb: CallbackQuery, state: FSMContext) -> None:
    result = await _save_new_mod(state, "")
    if result is None:
        await safe_edit(cb, T.ADMIN_STATE_LOST, AK.admin_menu_kb())
    else:
        mod_id, name = result
        await safe_edit(cb, T.mod_added(mod_id, name), AK.after_add_kb(mod_id))
    await cb.answer()


@router.message(AddMod.instructions)
async def add_instructions_wrong(message: Message) -> None:
    await message.answer(T.ERR_NEED_TEXT)


@router.message(AddMod.name)
@router.message(AddMod.description)
@router.message(AddMod.author)
async def add_text_wrong(message: Message) -> None:
    await message.answer(T.ERR_NEED_TEXT)


# ======================================================== MODLARNI BOSHQARISH
async def _manage_list_view(page: int):
    rows, total, page = await q.list_mods("all", 0, page)
    pages = _pages(total)
    return T.admin_list_text(total, page, pages), AK.mods_manage_kb(rows, page, pages)


@router.callback_query(F.data.startswith("adm:edl:"))
async def cb_edit_list(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, kb = await _manage_list_view(int(cb.data.split(":")[2]))
    await safe_edit(cb, text, kb)
    await cb.answer()


async def _edit_menu_view(mod_id: int):
    mod = await q.get_mod(mod_id)
    if not mod:
        return T.MOD_NOT_FOUND, AK.list_back_kb()
    return T.admin_edit_text(mod), AK.edit_menu_kb(mod_id)


@router.callback_query(F.data.startswith("adm:ed:"))
async def cb_edit_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, kb = await _edit_menu_view(int(cb.data.split(":")[2]))
    await safe_edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ef:"))
async def cb_edit_field(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, mod_id, field = cb.data.split(":")
    mod_id = int(mod_id)
    if not await q.get_mod(mod_id):
        await cb.answer(T.MOD_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.update_data(mod_id=mod_id, field=field)

    if field in FIELD_LIMITS:
        low, high = FIELD_LIMITS[field]
        hint = "\n<i>Tozalash uchun «-» yuboring.</i>" if field == "instructions" else ""
        await state.set_state(EditMod.value)
        text = (
            f"✏️ Yangi <b>{T.EDIT_FIELD_LABELS[field]}</b> yuboring "
            f"(maksimal {high} belgi).{hint}"
        )
    elif field == "preview":
        await state.set_state(EditMod.preview)
        text = T.EDIT_PHOTO
    elif field == "file":
        await state.set_state(EditMod.file)
        text = T.EDIT_FILE
    else:
        await cb.answer(T.STALE_BUTTON, show_alert=True)
        return
    await safe_edit(cb, text, AK.edit_back_kb(mod_id))
    await cb.answer()


async def _reply_edit_menu(message: Message, mod_id: int) -> None:
    text, kb = await _edit_menu_view(mod_id)
    await message.answer(f"{T.EDIT_DONE}\n\n{text}", reply_markup=kb)


@router.message(EditMod.value, PlainText())
async def edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    mod_id, field = data.get("mod_id"), data.get("field")
    if mod_id is None or field not in FIELD_LIMITS:
        await state.clear()
        await message.answer(T.ADMIN_STATE_LOST, reply_markup=AK.admin_menu_kb())
        return

    value = " ".join(message.text.split()) if field in ("name", "author") else message.text.strip()
    if field == "instructions" and value == "-":
        value = ""
    low, high = FIELD_LIMITS[field]
    if not low <= len(value) <= high:
        await message.answer(FIELD_ERRORS[field])
        return

    await q.update_mod_field(mod_id, field, value)
    await state.clear()
    await _reply_edit_menu(message, mod_id)


@router.message(EditMod.preview, F.photo)
async def edit_preview(message: Message, state: FSMContext) -> None:
    mod_id = (await state.get_data()).get("mod_id")
    if mod_id is None:
        await state.clear()
        await message.answer(T.ADMIN_STATE_LOST, reply_markup=AK.admin_menu_kb())
        return
    await q.update_mod_field(mod_id, "preview_file_id", message.photo[-1].file_id)
    await state.clear()
    await _reply_edit_menu(message, mod_id)


@router.message(EditMod.file, F.document)
async def edit_file(message: Message, state: FSMContext) -> None:
    mod_id = (await state.get_data()).get("mod_id")
    if mod_id is None:
        await state.clear()
        await message.answer(T.ADMIN_STATE_LOST, reply_markup=AK.admin_menu_kb())
        return
    doc = message.document
    error = validate_document(doc)
    if error:
        await message.answer(error)
        return
    await q.update_mod_file(
        mod_id, doc.file_id, doc.file_unique_id, doc.file_name or "mod",
        doc.file_size or 0, file_extension(doc.file_name),
    )
    await state.clear()
    await _reply_edit_menu(message, mod_id)


@router.message(EditMod.value)
async def edit_value_wrong(message: Message) -> None:
    await message.answer(T.ERR_NEED_TEXT)


@router.message(EditMod.preview)
async def edit_preview_wrong(message: Message) -> None:
    await message.answer(T.ERR_NEED_PHOTO)


@router.message(EditMod.file)
async def edit_file_wrong(message: Message) -> None:
    await message.answer(T.ERR_NEED_DOCUMENT)


# -------------------------------------------------- kategoriya va versiyalarni o'zgartirish
@router.callback_query(F.data.startswith("adm:ec:"))
async def cb_edit_category(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    mod_id = int(cb.data.split(":")[2])
    cats = await q.get_categories()
    kb = AK.categories_pick_kb(cats, f"adm:ecs:{mod_id}", f"adm:ed:{mod_id}", "⬅️ Orqaga")
    await safe_edit(cb, T.EDIT_CATEGORY, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ecs:"))
async def cb_edit_category_set(cb: CallbackQuery) -> None:
    _, _, mod_id, cat_id = cb.data.split(":")
    if not await q.get_category(int(cat_id)) or not await q.get_mod(int(mod_id)):
        await cb.answer(T.STALE_BUTTON, show_alert=True)
        return
    await q.update_mod_field(int(mod_id), "category_id", int(cat_id))
    text, kb = await _edit_menu_view(int(mod_id))
    await safe_edit(cb, f"{T.EDIT_DONE}\n\n{text}", kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ev:"))
async def cb_edit_versions(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, mod_id, action = cb.data.split(":")
    mod_id = int(mod_id)
    mod = await q.get_mod(mod_id)
    if not mod:
        await cb.answer(T.MOD_NOT_FOUND, show_alert=True)
        return

    if action == "done":
        text, kb = await _edit_menu_view(mod_id)
        await safe_edit(cb, f"{T.EDIT_DONE}\n\n{text}", kb)
        await cb.answer()
        return

    selected = set(parse_versions(mod["versions"]))
    if action != "open":
        if action not in config.MC_VERSIONS:
            await cb.answer(T.STALE_BUTTON, show_alert=True)
            return
        selected ^= {action}
        await q.update_mod_field(mod_id, "versions", join_versions(selected))

    kb = AK.versions_toggle_kb(selected, f"adm:ev:{mod_id}", f"adm:ed:{mod_id}", "⬅️ Orqaga")
    await safe_edit(cb, T.EDIT_VERSIONS, kb)
    await cb.answer()


# ---------------------------------------------------------------------- o'chirish
@router.callback_query(F.data.startswith("adm:del:"))
async def cb_delete_confirm(cb: CallbackQuery) -> None:
    mod = await q.get_mod(int(cb.data.split(":")[2]))
    if not mod:
        await cb.answer(T.MOD_NOT_FOUND, show_alert=True)
        return
    await safe_edit(cb, T.admin_delete_confirm(mod), AK.delete_confirm_kb(mod["id"]))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:delok:"))
async def cb_delete_do(cb: CallbackQuery) -> None:
    await q.delete_mod(int(cb.data.split(":")[2]))
    text, kb = await _manage_list_view(0)
    await safe_edit(cb, f"{T.DELETE_DONE}\n\n{text}", kb)
    await cb.answer(T.DELETE_DONE)


# ================================================================== SO'ROVLAR
async def _requests_list_view(status: str, page: int):
    rows, total, page = await q.list_requests(status, page)
    pages = _pages(total)
    return (
        T.admin_requests_text(status, total, page, pages),
        AK.requests_list_kb(rows, status, page, pages),
    )


async def _request_view(req_id: int, fstatus: str, page: int):
    req = await q.get_request(req_id)
    if not req:
        return T.REQUEST_NOT_FOUND, AK.requests_back_kb(fstatus, page)
    return T.admin_request_text(req), AK.request_view_kb(req, fstatus, page)


@router.callback_query(F.data.startswith("adm:rq:"))
async def cb_requests(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, status, page = cb.data.split(":")
    if status not in config.REQUEST_STATUSES:
        await cb.answer(T.STALE_BUTTON, show_alert=True)
        return
    text, kb = await _requests_list_view(status, int(page))
    await safe_edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:rv:"))
async def cb_request_view(cb: CallbackQuery) -> None:
    _, _, req_id, fstatus, page = cb.data.split(":")
    text, kb = await _request_view(int(req_id), fstatus, int(page))
    await safe_edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:rs:"))
async def cb_request_status(cb: CallbackQuery) -> None:
    _, _, req_id, new_status, fstatus, page = cb.data.split(":")
    req_id, page = int(req_id), int(page)
    if new_status not in config.REQUEST_STATUSES:
        await cb.answer(T.STALE_BUTTON, show_alert=True)
        return
    req = await q.get_request(req_id)
    if not req:
        await cb.answer(T.REQUEST_NOT_FOUND, show_alert=True)
        return

    if req["status"] != new_status:
        await q.set_request_status(req_id, new_status)
        notice = T.request_status_user(req, new_status)
        if notice:
            try:
                await cb.bot.send_message(req["user_id"], notice)
            except TelegramAPIError as exc:
                log.info("So'rov egasiga xabar yuborilmadi (%s): %s", req["user_id"], exc)

    text, kb = await _request_view(req_id, fstatus, page)
    await safe_edit(cb, text, kb)
    await cb.answer("✅ Holat yangilandi")
