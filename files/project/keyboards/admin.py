"""Admin panel klaviaturalari."""
from typing import List, Optional, Set

from aiogram.types import InlineKeyboardMarkup

import config
from keyboards.inline import btn, grid, markup, menu_btn, pager_row
from utils.helpers import trunc
from utils.texts import STATUS_LABELS


def admin_menu_kb() -> InlineKeyboardMarkup:
    return markup([
        [btn("➕ Mod qo'shish", "adm:add"), btn("✏️ Modlarni boshqarish", "adm:edl:0")],
        [btn("📨 So'rovlar", "adm:rq:pending:0"), btn("📊 Statistika", "adm:stats")],
        [menu_btn()],
    ])


def panel_back_kb() -> InlineKeyboardMarkup:
    return markup([[btn("🛠 Admin panel", "adm:home"), menu_btn()]])


def cancel_kb() -> InlineKeyboardMarkup:
    return markup([[btn("❌ Bekor qilish", "adm:cancel")]])


def instructions_skip_kb() -> InlineKeyboardMarkup:
    return markup([
        [btn("⏭ Standart yo'riqnoma", "adm:askip")],
        [btn("❌ Bekor qilish", "adm:cancel")],
    ])


def categories_pick_kb(cats: list, prefix: str, back_data: str, back_label: str) -> InlineKeyboardMarkup:
    buttons = [btn(f"{c['emoji']} {c['name']}", f"{prefix}:{c['id']}") for c in cats]
    rows = grid(buttons, 2)
    rows.append([btn(back_label, back_data)])
    return markup(rows)


def versions_toggle_kb(selected: Set[str], prefix: str, back_data: str, back_label: str) -> InlineKeyboardMarkup:
    buttons = [
        btn(f"{'✅' if v in selected else '◻️'} {v}", f"{prefix}:{v}") for v in config.MC_VERSIONS
    ]
    rows = grid(buttons, 3)
    rows.append([btn("✔️ Tayyor", f"{prefix}:done")])
    rows.append([btn(back_label, back_data)])
    return markup(rows)


def after_add_kb(mod_id: int) -> InlineKeyboardMarkup:
    return markup([
        [btn("👁 Modni ko'rish", f"mod:{mod_id}:all:0:0")],
        [btn("➕ Yana qo'shish", "adm:add"), btn("🛠 Admin panel", "adm:home")],
    ])


# ------------------------------------------------------------ modlarni boshqarish
def mods_manage_kb(rows: list, page: int, pages: int) -> InlineKeyboardMarkup:
    kb: List[list] = [[btn(f"#{m['id']} {trunc(m['name'], 32)}", f"adm:ed:{m['id']}")] for m in rows]
    if pages > 1:
        kb.append(pager_row(page, pages, "adm:edl"))
    kb.append([btn("🛠 Admin panel", "adm:home"), menu_btn()])
    return markup(kb)


def edit_menu_kb(mod_id: int) -> InlineKeyboardMarkup:
    return markup([
        [btn("📝 Nomi", f"adm:ef:{mod_id}:name"), btn("📄 Tavsifi", f"adm:ef:{mod_id}:description")],
        [btn("👤 Muallif", f"adm:ef:{mod_id}:author"), btn("📂 Kategoriya", f"adm:ec:{mod_id}")],
        [btn("🎯 Versiyalar", f"adm:ev:{mod_id}:open"), btn("📖 Yo'riqnoma", f"adm:ef:{mod_id}:instructions")],
        [btn("🖼 Preview", f"adm:ef:{mod_id}:preview"), btn("📦 Fayl", f"adm:ef:{mod_id}:file")],
        [btn("👁 Foydalanuvchi ko'rinishi", f"mod:{mod_id}:all:0:0")],
        [btn("🗑 O'chirish", f"adm:del:{mod_id}")],
        [btn("⬅️ Ro'yxat", "adm:edl:0"), btn("🛠 Admin panel", "adm:home")],
    ])


def edit_back_kb(mod_id: int) -> InlineKeyboardMarkup:
    return markup([[btn("⬅️ Orqaga", f"adm:ed:{mod_id}")]])


def list_back_kb() -> InlineKeyboardMarkup:
    return markup([[btn("⬅️ Ro'yxat", "adm:edl:0"), btn("🛠 Admin panel", "adm:home")]])


def delete_confirm_kb(mod_id: int) -> InlineKeyboardMarkup:
    return markup([
        [btn("✅ Ha, o'chirish", f"adm:delok:{mod_id}")],
        [btn("❌ Yo'q", f"adm:ed:{mod_id}")],
    ])


# ----------------------------------------------------------------- so'rovlar
def requests_list_kb(rows: list, status: str, page: int, pages: int) -> InlineKeyboardMarkup:
    tabs = []
    for st in config.REQUEST_STATUSES:
        label = STATUS_LABELS[st]
        if st == status:
            label = f"▪️ {label}"
        tabs.append(btn(label, f"adm:rq:{st}:0"))
    kb: List[list] = grid(tabs, 2)
    for r in rows:
        kb.append([btn(f"#{r['id']} · {trunc(r['text'], 36)}", f"adm:rv:{r['id']}:{status}:{page}")])
    if pages > 1:
        kb.append(pager_row(page, pages, f"adm:rq:{status}"))
    kb.append([btn("🛠 Admin panel", "adm:home"), menu_btn()])
    return markup(kb)


def request_view_kb(req, fstatus: str, page: int) -> InlineKeyboardMarkup:
    action_labels = {
        "approved": "✅ Tasdiqlash",
        "rejected": "❌ Rad etish",
        "completed": "🎉 Bajarildi",
        "pending": "⏳ Kutilmoqdaga",
    }
    buttons = [
        btn(action_labels[st], f"adm:rs:{req['id']}:{st}:{fstatus}:{page}")
        for st in ("approved", "rejected", "completed", "pending")
        if st != req["status"]
    ]
    rows = grid(buttons, 2)
    rows.append([btn("⬅️ Ro'yxat", f"adm:rq:{fstatus}:{page}"), btn("🛠 Admin panel", "adm:home")])
    return markup(rows)


def requests_back_kb(fstatus: str, page: int) -> InlineKeyboardMarkup:
    return markup([[btn("⬅️ Ro'yxat", f"adm:rq:{fstatus}:{page}"), btn("🛠 Admin panel", "adm:home")]])
