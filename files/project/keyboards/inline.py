"""Foydalanuvchi uchun inline klaviaturalar."""
from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from utils.helpers import compat_state, trunc


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def menu_btn() -> InlineKeyboardButton:
    return btn("🏠 Bosh menyu", "menu")


def markup(rows: List[list]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def grid(buttons: list, cols: int) -> List[list]:
    return [buttons[i:i + cols] for i in range(0, len(buttons), cols)]


def pager_row(page: int, pages: int, prefix: str) -> list:
    row = []
    if page > 0:
        row.append(btn("⬅️ Oldingi", f"{prefix}:{page - 1}"))
    row.append(btn(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        row.append(btn("Keyingi ➡️", f"{prefix}:{page + 1}"))
    return row


# ------------------------------------------------------------------ menyu
def main_menu_kb(is_admin_user: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [btn("📦 Barcha modlar", "lst:all:0:0"), btn("🔍 Mod qidirish", "search")],
        [btn("🏆 Mashhur modlar", "lst:pop:0:0"), btn("🆕 Yangi modlar", "lst:new:0:0")],
        [btn("⭐ Sevimlilar", "lst:fav:0:0"), btn("📂 Kategoriyalar", "cats")],
        [btn("🎮 Minecraft versiyalari", "vers"), btn("💡 Mod so'rash", "req")],
        [btn("ℹ️ Yordam", "help")],
    ]
    if is_admin_user:
        rows.append([btn("🛠 Admin panel", "adm:home")])
    return markup(rows)


def menu_only_kb() -> InlineKeyboardMarkup:
    return markup([[menu_btn()]])


# ---------------------------------------------------------------- ro'yxat
_MARKS = {"ok": "✅", "no": "❌", "unverified": "⚠️", None: "📦"}


def mods_list_kb(
    rows: list, kind: str, arg: int, page: int, pages: int,
    user_version: Optional[str], extra_rows: Optional[List[list]] = None,
) -> InlineKeyboardMarkup:
    kb: List[list] = []
    for m in rows:
        mark = _MARKS[compat_state(m["versions"], user_version)]
        label = f"{mark} {trunc(m['name'], 28)} · ⬇️{m['downloads']}"
        kb.append([btn(label, f"mod:{m['id']}:{kind}:{arg}:{page}")])
    if pages > 1:
        kb.append(pager_row(page, pages, f"lst:{kind}:{arg}"))
    if extra_rows:
        kb.extend(extra_rows)
    bottom = []
    if kind == "cat":
        bottom.append(btn("⬅️ Kategoriyalar", "cats"))
    bottom.append(menu_btn())
    kb.append(bottom)
    return markup(kb)


def search_filter_rows(category_name: Optional[str], version_on: bool) -> List[list]:
    cat_label = trunc(category_name, 18) if category_name else "Hammasi"
    ver_label = "Ha" if version_on else "Yo'q"
    return [
        [btn(f"📂 Kategoriya: {cat_label}", "sfc"), btn(f"🎮 Mos versiya: {ver_label}", "sfv")],
        [btn("🔍 Yangi qidiruv", "search")],
    ]


def search_categories_kb(cats: list) -> InlineKeyboardMarkup:
    buttons = [btn("📂 Hammasi", "sfc:0")]
    buttons += [btn(f"{c['emoji']} {c['name']}", f"sfc:{c['id']}") for c in cats]
    rows = grid(buttons, 2)
    rows.append([btn("⬅️ Orqaga", "lst:srch:0:0"), menu_btn()])
    return markup(rows)


def search_retry_kb() -> InlineKeyboardMarkup:
    return markup([[btn("🔍 Qidirish", "search")], [menu_btn()]])


def categories_kb(cats: list) -> InlineKeyboardMarkup:
    buttons = [
        btn(f"{c['emoji']} {c['name']} ({c['mods_count']})", f"lst:cat:{c['id']}:0") for c in cats
    ]
    rows = grid(buttons, 2)
    rows.append([menu_btn()])
    return markup(rows)


# -------------------------------------------------------------- mod kartasi
def mod_card_kb(mod_id: int, is_fav: bool, kind: str, arg: int, page: int, is_admin_user: bool) -> InlineKeyboardMarkup:
    ctx = f"{kind}:{arg}:{page}"
    fav_label = "💔 Sevimlilardan olib tashlash" if is_fav else "⭐ Sevimlilarga qo'shish"
    rows = [
        [btn("⬇️ Yuklab olish", f"dl:{mod_id}")],
        [btn(fav_label, f"fv:{mod_id}:{ctx}")],
        [btn("📖 O'rnatish yo'riqnomasi", f"ins:{mod_id}:{ctx}")],
    ]
    if is_admin_user:
        rows.append([btn("✏️ Tahrirlash (admin)", f"adm:ed:{mod_id}")])
    rows.append([btn("⬅️ Orqaga", f"lst:{ctx}"), menu_btn()])
    return markup(rows)


def instructions_kb(mod_id: int, kind: str, arg: int, page: int) -> InlineKeyboardMarkup:
    ctx = f"{kind}:{arg}:{page}"
    return markup([
        [btn("⬇️ Yuklab olish", f"dl:{mod_id}")],
        [btn("⬅️ Mod ma'lumotlari", f"mod:{mod_id}:{ctx}"), menu_btn()],
    ])


# ---------------------------------------------------------------- versiyalar
def versions_kb(current: Optional[str]) -> InlineKeyboardMarkup:
    buttons = [btn(f"✅ {v}" if v == current else v, f"setv:{v}") for v in config.MC_VERSIONS]
    rows = grid(buttons, 3)
    if current:
        rows.append([btn("📋 Mos modlarni ko'rish", "lst:ver:0:0")])
        rows.append([btn("🚫 Filtrni o'chirish", "clrv")])
    rows.append([menu_btn()])
    return markup(rows)


# ---------------------------------------------------------------- so'rovlar
def request_menu_kb() -> InlineKeyboardMarkup:
    return markup([[btn("✍️ Yangi so'rov yuborish", "reqnew")], [menu_btn()]])


def request_cancel_kb() -> InlineKeyboardMarkup:
    return markup([[btn("⬅️ Orqaga", "req"), menu_btn()]])
