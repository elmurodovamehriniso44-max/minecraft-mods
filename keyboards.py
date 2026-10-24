from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from texts import CATEGORIES


def b(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Foydalanuvchi ----------
def main_menu():
    return kb([
        [b("📂 Katalog", "catalog")],
        [b("🔍 Qidirish", "search")],
        [b("ℹ️ O'rnatish yo'riqnomasi", "guide")],
    ])


def categories():
    rows = [[b(name, f"cat:{key}")] for key, name in CATEGORIES.items()]
    rows.append([b("🏠 Menyu", "home")])
    return kb(rows)


def versions(category: str, versions_list: list[str]):
    rows = [[b("🌐 Hammasi", f"v:{category}:all")]]
    row = []
    for v in versions_list:
        row.append(b(f"🎮 {v}", f"v:{category}:{v}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([b("🔙 Ortga", "catalog")])
    return kb(rows)


def card_kb(mod, nav=None):
    rows = []
    if nav:
        cat, ver, idx, total = nav
        if total > 1:
            rows.append([
                b("⬅️ Ortga", f"n:{cat}:{ver}:{idx - 1}"),
                b(f"{idx + 1}/{total}", "noop"),
                b("➡️ Keyingisi", f"n:{cat}:{ver}:{idx + 1}"),
            ])
    rows.append([b("📥 Yuklab olish", f"dl:{mod.id}")])
    extra = []
    if len(mod.photo_list) > 1:
        extra.append(b("🖼 Skrinshotlar", f"ss:{mod.id}"))
    extra.append(b("ℹ️ Qanday o'rnatiladi?", "guide"))
    rows.append(extra)
    if nav:
        rows.append([b("🔙 Versiyalar", f"cat:{nav[0]}"), b("🏠 Menyu", "home")])
    else:
        rows.append([b("🏠 Menyu", "home")])
    return kb(rows)


def after_download():
    return kb([
        [b("ℹ️ Qanday o'rnatiladi?", "guide")],
        [b("📂 Katalog", "catalog"), b("🏠 Menyu", "home")],
    ])


def search_results(mods):
    rows = [[b(f"{m.title[:35]} • {m.version}", f"m:{m.id}")] for m in mods]
    rows.append([b("🏠 Menyu", "home")])
    return kb(rows)


def guide_os():
    return kb([
        [b("🤖 Android", "g:android"), b("🍎 iOS", "g:ios")],
        [b("💻 Windows", "g:windows")],
        [b("❌ Yopish", "close")],
    ])


# ---------- Admin ----------
def admin_menu():
    return kb([
        [b("➕ Yangi qo'shish", "adm:add")],
        [b("✏️ Tahrirlash", "adm:l:e:0"), b("🗑 O'chirish", "adm:l:d:0")],
        [b("📢 Xabar yuborish", "adm:bc"), b("📊 Statistika", "adm:stats")],
    ])


def admin_categories(prefix: str):
    return kb([[b(name, f"{prefix}{key}")] for key, name in CATEGORIES.items()])


def mods_list(mods, mode: str, page: int, total: int, per: int = 8):
    rows = [[b(f"#{m.id} {m.title[:30]} • {m.version}", f"adm:{mode}:{m.id}")] for m in mods]
    nav = []
    if page > 0:
        nav.append(b("⬅️", f"adm:l:{mode}:{page - 1}"))
    if (page + 1) * per < total:
        nav.append(b("➡️", f"adm:l:{mode}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([b("🔙 Panel", "adm:home")])
    return kb(rows)


def edit_fields(mod_id: int):
    f = lambda t, k: b(t, f"adm:ef:{mod_id}:{k}")
    return kb([
        [f("📝 Nomi", "title"), f("📄 Tavsif", "description")],
        [f("📂 Bo'lim", "category"), f("🎮 Versiya", "version")],
        [f("🏷 Teglar", "tags"), f("🖼 Rasmlar", "photos")],
        [f("📦 Fayl", "file")],
        [b("🔙 Ro'yxat", "adm:l:e:0")],
    ])


def confirm_delete(mod_id: int):
    return kb([[b("✅ Ha, o'chirish", f"adm:dy:{mod_id}"), b("❌ Yo'q", "adm:l:d:0")]])


def photos_done(data: str):
    return kb([[b("✅ Rasmlar tayyor", data)]])


def confirm_broadcast():
    return kb([[b("✅ Yuborish", "bc:yes"), b("❌ Bekor", "bc:no")]])
