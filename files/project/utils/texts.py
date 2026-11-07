"""Barcha foydalanuvchi matnlari (o'zbek tili, lotin alifbosi)."""
import config
from utils.helpers import compat_state, esc, fmt_size, parse_versions, trunc

# ------------------------------------------------------------------ umumiy
MAIN_MENU = "🏠 <b>Bosh menyu</b>\n\nKerakli bo'limni tanlang 👇"

RATE_LIMIT = "⏳ Juda tez harakat qilyapsiz. Iltimos, biroz kuting."
ERROR_GENERIC = "😔 Kutilmagan xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring."
NO_PERMISSION = "⛔ Sizda bu amal uchun ruxsat yo'q."
STALE_BUTTON = "⚠️ Bu tugma eskirgan. Iltimos, /start buyrug'ini yuboring."
CANCELLED = "❌ Amal bekor qilindi."
USE_MENU = "Iltimos, quyidagi menyudan foydalaning 👇"
NEED_TEXT = "✍️ Iltimos, matn yuboring (buyruq emas)."

HELP = (
    "ℹ️ <b>Yordam</b>\n\n"
    "<b>Bo'limlar:</b>\n"
    "📦 <b>Barcha modlar</b> — to'liq katalog\n"
    "🔍 <b>Mod qidirish</b> — nom yoki kalit so'z bo'yicha (imlo xatosi bo'lsa ham topadi)\n"
    "🏆 <b>Mashhur modlar</b> — eng ko'p yuklanganlar\n"
    "🆕 <b>Yangi modlar</b> — oxirgi qo'shilganlar\n"
    "⭐ <b>Sevimlilar</b> — o'zingiz saqlagan modlar\n"
    "📂 <b>Kategoriyalar</b> — turkum bo'yicha ko'rish\n"
    "🎮 <b>Minecraft versiyalari</b> — versiyangizni tanlang, mos modlar belgilanadi\n"
    "💡 <b>Mod so'rash</b> — katalogda yo'q modni so'rang\n\n"
    "<b>O'rnatish:</b>\n"
    "1️⃣ Modni oching va «⬇️ Yuklab olish» tugmasini bosing.\n"
    "2️⃣ Yuklangan fayl (.mcaddon, .mcpack yoki .mcworld) ustiga bosing.\n"
    "3️⃣ Minecraft avtomatik ochilib, faylni import qiladi.\n"
    "4️⃣ Dunyo sozlamalarida Behavior va Resource Pack'ni yoqing.\n\n"
    "<b>Belgilar:</b>\n"
    "✅ versiyangizga mos · ⚠️ moslik tekshirilmagan · ❌ mos emas\n\n"
    "<b>Buyruqlar:</b>\n"
    "/start — botni boshlash\n"
    "/menu — bosh menyu\n"
    "/help — yordam\n"
    "/cancel — joriy amalni bekor qilish"
)


def welcome(name: str) -> str:
    return (
        f"👋 <b>Assalomu alaykum, {esc(name)}!</b>\n\n"
        "🎮 <b>Minecraft Bedrock Addons</b> botiga xush kelibsiz!\n\n"
        "Bu yerda siz:\n"
        "• 📦 addon, mod, shader va xaritalarni topasiz,\n"
        "• 🔍 nom bo'yicha tez qidirasiz,\n"
        "• ⭐ sevimlilaringizni saqlaysiz,\n"
        "• ⬇️ fayllarni to'g'ridan-to'g'ri Telegram orqali yuklab olasiz.\n\n"
        "Boshlash uchun bo'limni tanlang 👇"
    )


# ------------------------------------------------------------------ ro'yxat
LIST_TITLES = {
    "all": "📦 <b>Barcha modlar</b>",
    "pop": "🏆 <b>Mashhur modlar</b>",
    "new": "🆕 <b>Yangi modlar</b>",
    "fav": "⭐ <b>Sevimlilar</b>",
}

EMPTY_TEXTS = {
    "all": "Hozircha katalogda modlar yo'q.",
    "pop": "Hozircha katalogda modlar yo'q.",
    "new": "Hozircha katalogda modlar yo'q.",
    "fav": "Sevimlilar ro'yxatingiz bo'sh.\n\nMod sahifasidagi «⭐ Sevimlilarga qo'shish» tugmasini bosing.",
    "cat": "Bu kategoriyada hozircha modlar yo'q.",
    "srch": "😕 Hech narsa topilmadi.\n\nBoshqa so'z bilan urinib ko'ring yoki filtrlarni o'zgartiring.",
}


def list_text(kind: str, title: str, total: int, page: int, pages: int, user_version) -> str:
    if total == 0:
        if kind == "ver":
            if user_version:
                empty = (
                    f"Minecraft <b>{esc(user_version)}</b> uchun tasdiqlangan modlar topilmadi.\n"
                    "Versiya filtrini o'chirib, barcha modlarni ko'rishingiz mumkin."
                )
            else:
                empty = "Avval Minecraft versiyangizni tanlang."
        else:
            empty = EMPTY_TEXTS.get(kind, EMPTY_TEXTS["all"])
        return f"{title}\n\n{empty}"
    lines = [title, "", f"Jami: <b>{total}</b> ta  |  Sahifa: <b>{page + 1}/{pages}</b>"]
    if user_version:
        lines.append(f"🎮 Versiyangiz: <b>{esc(user_version)}</b>")
        lines.append("✅ mos · ⚠️ tekshirilmagan · ❌ mos emas")
    lines.append("")
    lines.append("Modni tanlang 👇")
    return "\n".join(lines)


def search_title(query: str) -> str:
    return f"🔍 <b>Qidiruv:</b> {esc(trunc(query, 40))}"


def category_title(name: str, emoji: str) -> str:
    return f"{esc(emoji)} <b>{esc(name)}</b>"


def version_list_title(version: str) -> str:
    return f"🎮 <b>Minecraft {esc(version)} uchun modlar</b>"


SEARCH_PROMPT = (
    "🔍 <b>Mod qidirish</b>\n\n"
    "Mod nomini yoki kalit so'zni yozing.\n"
    "Masalan: <i>zombie</i>, <i>qilich</i>, <i>mashina</i>\n\n"
    "Imlo xatolari bo'lsa ham qidiruv ishlaydi 😉"
)
SEARCH_EXPIRED = "⌛ Qidiruv natijalari eskirgan. Iltimos, qaytadan qidiring."
SEARCH_BAD_LENGTH = "⚠️ Qidiruv matni 2 dan 60 gacha belgidan iborat bo'lishi kerak."
SEARCH_PICK_CATEGORY = "📂 Qidiruv uchun kategoriyani tanlang:"
SEARCH_NEED_VERSION = (
    "Avval Minecraft versiyangizni tanlang: «🎮 Minecraft versiyalari» bo'limiga o'ting."
)

# ------------------------------------------------------------- kategoriyalar
CATEGORIES_TEXT = "📂 <b>Kategoriyalar</b>\n\nKerakli turkumni tanlang 👇"


# --------------------------------------------------------------- versiyalar
def versions_text(current) -> str:
    now = f"<b>{esc(current)}</b>" if current else "<i>tanlanmagan</i>"
    return (
        "🎮 <b>Minecraft versiyalari</b>\n\n"
        "Bedrock versiyangizni tanlang — bot modlarni sizning versiyangizga moslab belgilaydi.\n\n"
        f"Hozirgi tanlov: {now}\n\n"
        "✅ mos · ⚠️ moslik tekshirilmagan · ❌ mos emas\n"
        "<i>Moslik faqat administrator kiritgan ma'lumotga asoslanadi.</i>"
    )


# ---------------------------------------------------------------------- mod
MOD_NOT_FOUND = "😕 Mod topilmadi. U o'chirilgan bo'lishi mumkin."
FILE_ERROR = "⚠️ Faylni yuborib bo'lmadi. Iltimos, administrator bilan bog'laning."
FILE_SENT = "✅ Fayl yuborildi!"

COMPAT_LABELS = {
    "ok": "✅ Sizning versiyangizga mos",
    "no": "❌ Sizning versiyangizga mos emas",
    "unverified": "⚠️ Moslik tekshirilmagan",
}

DEFAULT_INSTRUCTIONS = {
    ".mcaddon": (
        "1️⃣ Faylni yuklab oling.\n"
        "2️⃣ Fayl ustiga bosing va Minecraft orqali oching — addon avtomatik import qilinadi.\n"
        "3️⃣ Dunyo yarating yoki mavjud dunyoni tahrirlang.\n"
        "4️⃣ «Behavior Packs» va «Resource Packs» bo'limlaridan addonni faollashtiring.\n"
        "5️⃣ Agar addon talab qilsa, «Experiments» (eksperimental funksiyalar)ni yoqing."
    ),
    ".mcpack": (
        "1️⃣ Faylni yuklab oling.\n"
        "2️⃣ Fayl ustiga bosing va Minecraft orqali oching — pack avtomatik import qilinadi.\n"
        "3️⃣ Dunyo sozlamalarida «Resource Packs» yoki «Behavior Packs» bo'limidan packni yoqing."
    ),
    ".mcworld": (
        "1️⃣ Faylni yuklab oling.\n"
        "2️⃣ Fayl ustiga bosing va Minecraft orqali oching — xarita avtomatik import qilinadi.\n"
        "3️⃣ «O'ynash» bo'limidan yangi dunyoni tanlang."
    ),
    ".zip": (
        "1️⃣ Zip faylni yuklab oling va arxivdan chiqaring.\n"
        "2️⃣ Ichida .mcaddon, .mcpack yoki .mcworld fayllar bo'lsa, ularni ustiga bosib oching.\n"
        "3️⃣ Agar faqat papkalar bo'lsa, ularni com.mojang papkasidagi "
        "development_behavior_packs va development_resource_packs ichiga joylang."
    ),
}


def mod_card(mod, user_version, desc_limit: int = 500) -> str:
    versions = parse_versions(mod["versions"])
    versions_txt = ", ".join(versions) if versions else "ko'rsatilmagan"
    lines = [
        f"🎮 <b>{esc(mod['name'])}</b>",
        "",
        f"{esc(mod['category_emoji'])} Kategoriya: <b>{esc(mod['category_name'])}</b>",
        f"👤 Muallif: <b>{esc(mod['author']) or '—'}</b>",
        f"📁 Fayl: <code>{esc(trunc(mod['file_name'], 40))}</code>",
        f"💾 Hajmi: <b>{fmt_size(mod['file_size'])}</b>",
        f"🎯 Versiyalar: <b>{esc(versions_txt)}</b>",
    ]
    state = compat_state(mod["versions"], user_version)
    if state:
        lines.append(COMPAT_LABELS[state])
    lines.append(f"⬇️ Yuklashlar: <b>{mod['downloads']}</b>")
    if mod["description"] and desc_limit > 0:
        lines += ["", "📝 " + esc(trunc(mod["description"], desc_limit))]
    return "\n".join(lines)


def instructions_text(mod, limit: int = 500) -> str:
    raw = (mod["instructions"] or "").strip() or DEFAULT_INSTRUCTIONS.get(
        mod["file_type"], DEFAULT_INSTRUCTIONS[".zip"]
    )
    return (
        f"📖 <b>O'rnatish yo'riqnomasi</b>\n"
        f"🎮 <i>{esc(trunc(mod['name'], 60))}</i>\n\n"
        f"{esc(trunc(raw, limit))}"
    )


def download_caption(mod, limit: int = 500) -> str:
    head = f"✅ <b>{esc(trunc(mod['name'], 60))}</b> — {fmt_size(mod['file_size'])}\n\n"
    return head + instructions_text(mod, limit)


# ---------------------------------------------------------------- so'rovlar
STATUS_LABELS = {
    "pending": "⏳ Kutilmoqda",
    "approved": "✅ Tasdiqlangan",
    "rejected": "❌ Rad etilgan",
    "completed": "🎉 Bajarilgan",
}

REQUEST_ASK = (
    "✍️ <b>Mod so'rash</b>\n\n"
    "Qaysi modni qo'shishimizni xohlaysiz? Nomini va qisqacha tavsifini yozing (5–300 belgi).\n\n"
    "<i>Havolalar (link) qabul qilinmaydi.</i>"
)
REQUEST_BAD_LENGTH = "⚠️ So'rov matni 5 dan 300 gacha belgidan iborat bo'lishi kerak."
REQUEST_LINKS = "⚠️ So'rovda havola (link) bo'lishi mumkin emas. Faqat mod nomi va tavsifini yozing."
REQUEST_DAILY_LIMIT = (
    f"⚠️ Kuniga ko'pi bilan {config.REQUEST_DAILY_LIMIT} ta so'rov yuborish mumkin. "
    "Iltimos, ertaga qayta urinib ko'ring."
)
REQUEST_TOO_FAST = "⏳ Keyingi so'rovni yuborishdan oldin 1 daqiqa kuting."
REQUEST_DUPLICATE = (
    "ℹ️ Bu mod uchun so'rov allaqachon mavjud. Administratorlar uni ko'rib chiqishmoqda."
)
REQUEST_SENT = "✅ So'rovingiz yuborildi! Administratorlar ko'rib chiqadi va natijani sizga xabar qiladi."
REQUEST_NOT_FOUND = "😕 So'rov topilmadi."


def request_menu(mine) -> str:
    lines = [
        "💡 <b>Mod so'rash</b>",
        "",
        "Katalogda yo'q modni so'rang — administratorlar ko'rib chiqadi.",
        f"⚠️ Kuniga ko'pi bilan {config.REQUEST_DAILY_LIMIT} ta so'rov yuborish mumkin.",
    ]
    if mine:
        lines += ["", "📋 <b>Oxirgi so'rovlaringiz:</b>"]
        for r in mine:
            lines.append(
                f"#{r['id']} {STATUS_LABELS[r['status']]} — {esc(trunc(r['text'], 40))}"
            )
    return "\n".join(lines)


def request_notify_admin(req_id: int, user, text: str) -> str:
    uname = f" (@{esc(user.username)})" if user.username else ""
    return (
        f"📨 <b>Yangi mod so'rovi #{req_id}</b>\n\n"
        f"👤 {esc(user.full_name)}{uname}\n"
        f"🆔 <code>{user.id}</code>\n\n"
        f"📝 {esc(text)}"
    )


def request_status_user(req, status: str):
    quote = esc(trunc(req["text"], 80))
    if status == "approved":
        return f"✅ <b>#{req['id']}</b> raqamli so'rovingiz tasdiqlandi!\nTez orada modni qo'shishga harakat qilamiz.\n\n📝 {quote}"
    if status == "rejected":
        return f"❌ <b>#{req['id']}</b> raqamli so'rovingiz afsuski rad etildi.\n\n📝 {quote}"
    if status == "completed":
        return (
            f"🎉 <b>#{req['id']}</b> raqamli so'rovingiz bajarildi!\n"
            "Mod katalogga qo'shildi — «🆕 Yangi modlar» bo'limidan toping.\n\n"
            f"📝 {quote}"
        )
    return None


# -------------------------------------------------------------------- admin
ADMIN_HOME = "🛠 <b>Admin panel</b>\n\nKerakli amalni tanlang 👇"
ADMIN_CANCELLED = "❌ Amal bekor qilindi.\n\n" + ADMIN_HOME
ADMIN_STATE_LOST = "⚠️ Ma'lumotlar yo'qolgan. Iltimos, jarayonni qaytadan boshlang."

ADD_NAME = "➕ <b>Yangi mod qo'shish</b>\n\n1/8 — Mod <b>nomini</b> yuboring (2–60 belgi):"
ADD_DESC = "2/8 — Mod <b>tavsifini</b> yuboring (maksimal 500 belgi):"
ADD_CATEGORY = "3/8 — <b>Kategoriyani</b> tanlang:"
ADD_AUTHOR = "4/8 — Mod <b>muallifini</b> yuboring (maksimal 40 belgi):"
ADD_VERSIONS = (
    "5/8 — Mos keladigan <b>Minecraft versiyalarini</b> belgilang.\n"
    "<i>Hech narsa tanlanmasa, moslik «tekshirilmagan» deb belgilanadi.</i>"
)
ADD_PREVIEW = "6/8 — <b>Preview rasmini</b> yuboring (fayl emas, oddiy rasm sifatida):"
ADD_FILE = (
    "7/8 — <b>Mod faylini</b> yuboring.\n"
    "Ruxsat etilgan turlar: <b>.mcaddon, .mcpack, .mcworld, .zip</b>"
)
ADD_INSTRUCTIONS = (
    "8/8 — <b>O'rnatish yo'riqnomasini</b> yuboring (maksimal 500 belgi).\n"
    "Standart yo'riqnoma uchun pastdagi tugmani bosing."
)

ERR_NAME_LEN = "⚠️ Nom 2 dan 60 gacha belgidan iborat bo'lishi kerak. Qayta yuboring:"
ERR_DESC_LEN = "⚠️ Tavsif 1 dan 500 gacha belgidan iborat bo'lishi kerak. Qayta yuboring:"
ERR_AUTHOR_LEN = "⚠️ Muallif nomi 1 dan 40 gacha belgidan iborat bo'lishi kerak. Qayta yuboring:"
ERR_INSTR_LEN = "⚠️ Yo'riqnoma 500 belgidan oshmasligi kerak. Qayta yuboring:"
ERR_NEED_PHOTO = "🖼 Iltimos, rasmni <b>foto</b> sifatida yuboring (fayl sifatida emas)."
ERR_NEED_DOCUMENT = "📎 Iltimos, mod faylini <b>fayl (document)</b> sifatida yuboring."
ERR_NEED_TEXT = "✍️ Iltimos, matn yuboring."

EDIT_FIELD_LABELS = {
    "name": "nomini",
    "description": "tavsifini",
    "author": "muallifini",
    "instructions": "o'rnatish yo'riqnomasini",
}

EDIT_PHOTO = "🖼 Yangi <b>preview rasmini</b> foto sifatida yuboring:"
EDIT_FILE = "📦 Yangi <b>mod faylini</b> yuboring (.mcaddon, .mcpack, .mcworld, .zip):"
EDIT_VERSIONS = "🎯 Mos keladigan <b>Minecraft versiyalarini</b> belgilang (o'zgarishlar darhol saqlanadi):"
EDIT_CATEGORY = "📂 Yangi <b>kategoriyani</b> tanlang:"
EDIT_DONE = "✅ Mod yangilandi!"
DELETE_DONE = "🗑 Mod o'chirildi."


def mod_added(mod_id: int, name: str) -> str:
    return f"✅ <b>{esc(name)}</b> modi katalogga qo'shildi! (ID: <code>{mod_id}</code>)"


def admin_edit_text(mod) -> str:
    return f"✏️ <b>Modni tahrirlash</b> (ID: <code>{mod['id']}</code>)\n\n{mod_card(mod, None, 500)}\n\n🛠 <b>Nimani o'zgartirmoqchisiz?</b>"


def admin_delete_confirm(mod) -> str:
    return (
        f"🗑 <b>{esc(mod['name'])}</b> modini o'chirmoqchimisiz?\n\n"
        "⚠️ Mod, uning sevimlilar va yuklash tarixi o'chiriladi. Bu amalni qaytarib bo'lmaydi."
    )


def admin_list_text(total: int, page: int, pages: int) -> str:
    if total == 0:
        return "✏️ <b>Modlarni boshqarish</b>\n\nHozircha modlar yo'q. Avval «➕ Mod qo'shish» orqali qo'shing."
    return (
        f"✏️ <b>Modlarni boshqarish</b>\n\nJami: <b>{total}</b> ta  |  Sahifa: <b>{page + 1}/{pages}</b>\n\n"
        "Tahrirlash yoki o'chirish uchun modni tanlang 👇"
    )


def stats_text(s) -> str:
    lines = [
        "📊 <b>Statistika</b>",
        "",
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>",
        f"📦 Modlar: <b>{s['mods']}</b>",
        f"⬇️ Jami yuklashlar: <b>{s['downloads']}</b>",
        f"   • Bugun: <b>{s['today']}</b>",
        f"   • Oxirgi 7 kun: <b>{s['week']}</b>",
        f"⭐ Sevimlilarga qo'shilgan: <b>{s['favorites']}</b>",
        f"📨 Kutilayotgan so'rovlar: <b>{s['pending']}</b>",
    ]
    if s["top"]:
        lines += ["", "🏆 <b>Eng ko'p yuklangan modlar:</b>"]
        for i, row in enumerate(s["top"], 1):
            lines.append(f"{i}. {esc(trunc(row['name'], 35))} — <b>{row['downloads']}</b>")
    return "\n".join(lines)


def admin_requests_text(status: str, total: int, page: int, pages: int) -> str:
    head = f"📨 <b>Mod so'rovlari</b> — {STATUS_LABELS[status]}"
    if total == 0:
        return f"{head}\n\nBu holatda so'rovlar yo'q."
    return f"{head}\n\nJami: <b>{total}</b> ta  |  Sahifa: <b>{page + 1}/{pages}</b>"


def admin_request_text(r) -> str:
    uname = f" (@{esc(r['username'])})" if r["username"] else ""
    return (
        f"📨 <b>So'rov #{r['id']}</b>\n\n"
        f"👤 <a href=\"tg://user?id={r['user_id']}\">{esc(r['full_name'])}</a>{uname}\n"
        f"🆔 <code>{r['user_id']}</code>\n"
        f"🕒 {esc(r['created_at'][:16])}\n"
        f"📌 Holat: <b>{STATUS_LABELS[r['status']]}</b>\n\n"
        f"📝 {esc(r['text'])}"
    )
