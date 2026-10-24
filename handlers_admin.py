import asyncio

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
from config import config
from texts import CATEGORIES, esc, normalize_tags

router = Router()
router.message.filter(F.from_user.id.in_(config.admin_ids))
router.callback_query.filter(F.from_user.id.in_(config.admin_ids))

_bg_tasks: set = set()


class AddMod(StatesGroup):
    title = State()
    description = State()
    category = State()
    version = State()
    tags = State()
    photos = State()
    file = State()


class EditMod(StatesGroup):
    value = State()
    photos = State()
    file = State()


class Broadcast(StatesGroup):
    content = State()
    confirm = State()


PANEL = "🛠 <b>Admin panel</b>"


# ---------- Panel ----------
@router.message(Command("admin"))
async def admin_cmd(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(PANEL, reply_markup=kb.admin_menu())


@router.callback_query(F.data == "adm:home")
async def admin_home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await c.message.edit_text(PANEL, reply_markup=kb.admin_menu())
    except TelegramBadRequest:
        await c.message.answer(PANEL, reply_markup=kb.admin_menu())
    await c.answer()


# ---------- Yangi mod qo'shish ----------
@router.callback_query(F.data == "adm:add")
async def add_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddMod.title)
    await c.message.answer("1/7 📝 <b>Nomini</b> yuboring.\n\nBekor qilish: /cancel")
    await c.answer()


@router.message(AddMod.title, F.text)
async def add_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:120])
    await state.set_state(AddMod.description)
    await m.answer("2/7 📄 Qisqacha <b>tavsifni</b> o'zbek tilida yuboring.")


@router.message(AddMod.description, F.text)
async def add_desc(m: Message, state: FSMContext):
    await state.update_data(description=m.text.strip())
    await state.set_state(AddMod.category)
    await m.answer("3/7 📂 <b>Bo'limni</b> tanlang:", reply_markup=kb.admin_categories("acat:"))


@router.callback_query(AddMod.category, F.data.startswith("acat:"))
async def add_cat(c: CallbackQuery, state: FSMContext):
    await state.update_data(category=c.data.split(":")[1])
    await state.set_state(AddMod.version)
    await c.message.answer("4/7 🎮 <b>Minecraft versiyasi</b> (masalan: <code>1.21+</code> yoki <code>1.20</code>):")
    await c.answer()


@router.message(AddMod.version, F.text)
async def add_version(m: Message, state: FSMContext):
    v = m.text.strip()
    if len(v) > 15 or ":" in v:
        await m.answer("⚠️ Versiya qisqa bo'lsin (15 belgigacha, «:» siz). Qayta yuboring.")
        return
    await state.update_data(version=v)
    await state.set_state(AddMod.tags)
    await m.answer("5/7 🏷 <b>Teglar</b> (masalan: <code>avto qurol pvp 1_21</code>). Teg kerak bo'lmasa «-» yuboring.")


@router.message(AddMod.tags, F.text)
async def add_tags(m: Message, state: FSMContext):
    await state.update_data(tags=normalize_tags(m.text), photos=[])
    await state.set_state(AddMod.photos)
    await m.answer(
        "6/7 🖼 <b>Rasmlar/skrinshotlarni</b> yuboring (birinchisi muqova bo'ladi, jami 10 tagacha).\n"
        "Tugagach pastdagi tugmani bosing.",
        reply_markup=kb.photos_done("aphotos_done"),
    )


@router.message(AddMod.photos, F.photo)
async def add_photo(m: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) < 10:
        photos.append(m.photo[-1].file_id)
        await state.update_data(photos=photos)
    await m.answer(f"✅ Rasm qabul qilindi ({len(photos)}).", reply_markup=kb.photos_done("aphotos_done"))


@router.message(AddMod.photos)
async def add_photo_wrong(m: Message):
    await m.answer("Iltimos, rasm yuboring yoki «Rasmlar tayyor» ni bosing.")


@router.callback_query(AddMod.photos, F.data == "aphotos_done")
async def add_photos_done(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"):
        await c.answer("Kamida 1 ta rasm yuboring!", show_alert=True)
        return
    await state.set_state(AddMod.file)
    await c.message.answer(
        "7/7 📦 Endi <b>faylni</b> yuboring (<code>.mcaddon</code>, <code>.mcpack</code>, "
        "<code>.mctemplate</code>, <code>.mcworld</code> yoki <code>.zip</code>) — <b>hujjat (document)</b> sifatida."
    )
    await c.answer()


@router.message(AddMod.file, F.document)
async def add_file(m: Message, state: FSMContext):
    data = await state.get_data()
    mod = await db.add_mod(
        title=data["title"],
        description=data["description"],
        category=data["category"],
        version=data["version"],
        tags=data["tags"],
        photos=",".join(data["photos"]),
        file_id=m.document.file_id,
        file_name=m.document.file_name or "",
    )
    await state.clear()
    await m.answer(
        f"✅ <b>{esc(mod.title)}</b> saqlandi (ID: {mod.id}).", reply_markup=kb.admin_menu()
    )


@router.message(AddMod.file)
async def add_file_wrong(m: Message):
    await m.answer("Iltimos, faylni <b>hujjat</b> sifatida yuboring (📎 → File).")


# ---------- Tahrirlash / O'chirish ----------
@router.callback_query(F.data.startswith("adm:l:"))
async def list_mods(c: CallbackQuery):
    _, _, mode, page = c.data.split(":")
    page = int(page)
    mods, total = await db.list_mods_page(page)
    if not mods:
        await c.answer("Hozircha modlar yo'q", show_alert=True)
        return
    title = "✏️ Tahrirlash uchun tanlang:" if mode == "e" else "🗑 O'chirish uchun tanlang:"
    text = f"{title}\n(jami: {total})"
    markup = kb.mods_list(mods, mode, page, total)
    if c.message.text:
        try:
            await c.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass
    else:
        await c.message.answer(text, reply_markup=markup)
    await c.answer()


@router.callback_query(F.data.startswith("adm:e:"))
async def edit_pick(c: CallbackQuery):
    mod = await db.get_mod(int(c.data.split(":")[2]))
    if not mod:
        await c.answer("Topilmadi", show_alert=True)
        return
    await c.message.edit_text(
        f"✏️ <b>{esc(mod.title)}</b>\nQaysi maydonni o'zgartiramiz?", reply_markup=kb.edit_fields(mod.id)
    )
    await c.answer()


@router.callback_query(F.data.startswith("adm:ef:"))
async def edit_field(c: CallbackQuery, state: FSMContext):
    _, _, mod_id, field = c.data.split(":")
    mod_id = int(mod_id)
    await state.clear()
    await state.update_data(mod_id=mod_id, field=field, photos=[])
    if field == "category":
        await c.message.answer("Yangi bo'limni tanlang:", reply_markup=kb.admin_categories(f"adm:ec:{mod_id}:"))
    elif field == "photos":
        await state.set_state(EditMod.photos)
        await c.message.answer(
            "Yangi rasmlarni yuboring (eskilari almashtiriladi). Tugagach tugmani bosing.",
            reply_markup=kb.photos_done("ephotos_done"),
        )
    elif field == "file":
        await state.set_state(EditMod.file)
        await c.message.answer("Yangi faylni hujjat sifatida yuboring.")
    else:
        await state.set_state(EditMod.value)
        await c.message.answer("Yangi qiymatni yuboring (teglar uchun «-» = tozalash). Bekor: /cancel")
    await c.answer()


@router.callback_query(F.data.startswith("adm:ec:"))
async def edit_category(c: CallbackQuery):
    _, _, mod_id, cat = c.data.split(":")
    if cat in CATEGORIES:
        await db.update_mod(int(mod_id), category=cat)
    await c.message.edit_text("✅ Bo'lim yangilandi.", reply_markup=kb.admin_menu())
    await c.answer()


@router.message(EditMod.value, F.text)
async def edit_value(m: Message, state: FSMContext):
    data = await state.get_data()
    field, val = data["field"], m.text.strip()
    if field == "version" and (len(val) > 15 or ":" in val):
        await m.answer("⚠️ Versiya 15 belgidan oshmasin va «:» bo'lmasin.")
        return
    if field == "tags":
        val = normalize_tags(val)
    if field == "title":
        val = val[:120]
    await db.update_mod(data["mod_id"], **{field: val})
    await state.clear()
    await m.answer("✅ Yangilandi.", reply_markup=kb.admin_menu())


@router.message(EditMod.photos, F.photo)
async def edit_photo(m: Message, state: FSMContext):
    photos = (await state.get_data()).get("photos", [])
    if len(photos) < 10:
        photos.append(m.photo[-1].file_id)
        await state.update_data(photos=photos)
    await m.answer(f"✅ Rasm qabul qilindi ({len(photos)}).", reply_markup=kb.photos_done("ephotos_done"))


@router.callback_query(EditMod.photos, F.data == "ephotos_done")
async def edit_photos_done(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"):
        await c.answer("Kamida 1 ta rasm yuboring!", show_alert=True)
        return
    await db.update_mod(data["mod_id"], photos=",".join(data["photos"]))
    await state.clear()
    await c.message.answer("✅ Rasmlar yangilandi.", reply_markup=kb.admin_menu())
    await c.answer()


@router.message(EditMod.file, F.document)
async def edit_file(m: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_mod(data["mod_id"], file_id=m.document.file_id, file_name=m.document.file_name or "")
    await state.clear()
    await m.answer("✅ Fayl yangilandi.", reply_markup=kb.admin_menu())


@router.callback_query(F.data.startswith("adm:d:"))
async def delete_ask(c: CallbackQuery):
    mod = await db.get_mod(int(c.data.split(":")[2]))
    if not mod:
        await c.answer("Topilmadi", show_alert=True)
        return
    await c.message.edit_text(
        f"🗑 <b>{esc(mod.title)}</b> o'chirilsinmi?", reply_markup=kb.confirm_delete(mod.id)
    )
    await c.answer()


@router.callback_query(F.data.startswith("adm:dy:"))
async def delete_yes(c: CallbackQuery):
    await db.delete_mod(int(c.data.split(":")[2]))
    await c.message.edit_text("✅ O'chirildi.", reply_markup=kb.admin_menu())
    await c.answer()


# ---------- Statistika ----------
@router.callback_query(F.data == "adm:stats")
async def stats(c: CallbackQuery):
    users, mods, downloads, top = await db.get_stats()
    lines = [
        "📊 <b>Statistika</b>",
        "",
        f"👥 Foydalanuvchilar: <b>{users}</b>",
        f"📦 Fayllar: <b>{mods}</b>",
        f"📥 Jami yuklashlar: <b>{downloads}</b>",
        "",
        "🏆 <b>Eng ko'p yuklanganlar:</b>",
    ]
    if top:
        lines += [f"{i}. {esc(m.title)} — {m.downloads}" for i, m in enumerate(top, 1)]
    else:
        lines.append("— hozircha yo'q —")
    try:
        await c.message.edit_text("\n".join(lines), reply_markup=kb.admin_menu())
    except TelegramBadRequest:
        pass
    await c.answer()


# ---------- Rassilka ----------
@router.callback_query(F.data == "adm:bc")
async def bc_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Broadcast.content)
    await c.message.answer(
        "📢 Barcha foydalanuvchilarga yuboriladigan xabarni yuboring (matn, rasm, video — istalgan).\nBekor: /cancel"
    )
    await c.answer()


@router.message(Broadcast.content)
async def bc_content(m: Message, state: FSMContext):
    await state.update_data(chat_id=m.chat.id, message_id=m.message_id)
    await state.set_state(Broadcast.confirm)
    await m.answer("👆 Xabar shunday ko'rinadi. Yuboraymi?", reply_markup=kb.confirm_broadcast())


@router.callback_query(Broadcast.confirm, F.data.in_({"bc:yes", "bc:no"}))
async def bc_confirm(c: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    if c.data == "bc:no":
        await c.message.edit_text("❌ Bekor qilindi.", reply_markup=kb.admin_menu())
        await c.answer()
        return
    await c.message.edit_text("⏳ Yuborilmoqda... tugagach xabar beraman.")
    await c.answer()
    task = asyncio.create_task(_broadcast(bot, c.from_user.id, data["chat_id"], data["message_id"]))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _broadcast(bot: Bot, admin_id: int, from_chat: int, msg_id: int):
    sent = failed = 0
    for uid in await db.all_user_ids():
        for attempt in range(2):
            try:
                await bot.copy_message(uid, from_chat, msg_id)
                sent += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except (TelegramForbiddenError, TelegramBadRequest):
                failed += 1
                break
            except Exception:
                failed += 1
                break
        await asyncio.sleep(0.05)
    await bot.send_message(
        admin_id,
        f"📢 Rassilka tugadi.\n✅ Yetkazildi: <b>{sent}</b>\n🚫 Yetkazilmadi: <b>{failed}</b>",
        reply_markup=kb.admin_menu(),
    )
