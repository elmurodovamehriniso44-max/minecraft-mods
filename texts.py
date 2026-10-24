import html

from config import config

CATEGORIES = {
    "mod": "🧩 Modlar / Addonlar",
    "map": "🗺 Kartalar (Maps)",
    "texture": "🎨 Teksturalar",
    "skin": "👤 Skinlar",
    "shader": "✨ Shaderlar",
}

WELCOME = (
    "👋 <b>Minecraft Bedrock katalogiga xush kelibsiz!</b>\n\n"
    "Bu yerda modlar, kartalar, teksturalar, skinlar va shaderlarni "
    "bir bosishda yuklab olishingiz mumkin.\n\n"
    "💡 Qidirish uchun shunchaki so'z yozing: <i>furniture</i>, <i>gun</i>, <i>one block</i>"
)

GUIDE_INTRO = "ℹ️ <b>Qanday o'rnatiladi?</b>\n\nQurilmangizni tanlang:"

GUIDE = {
    "android": (
        "🤖 <b>Android</b>\n\n"
        "1️⃣ Botdan faylni yuklab oling (<code>.mcaddon</code>, <code>.mcpack</code> yoki <code>.mctemplate</code>).\n"
        "2️⃣ Fayl ustiga bosing yoki «Ochish» ni tanlang.\n"
        "3️⃣ Dastur sifatida <b>Minecraft</b> ni tanlang — o'yin o'zi ochilib, faylni import qiladi.\n"
        "4️⃣ «Import muvaffaqiyatli» chiqqach, dunyo sozlamalarida (Create/Edit World) "
        "<b>Behavior Packs</b> yoki <b>Resource Packs</b> bo'limidan yoqing.\n"
        "5️⃣ Addonlar uchun ba'zan <b>Experimental</b> funksiyalarni (Beta APIs, Holiday Creator Features) yoqish kerak.\n\n"
        "⚠️ Agar fayl <code>.zip</code> bo'lsa, avval arxivdan chiqaring."
    ),
    "ios": (
        "🍎 <b>iPhone / iPad</b>\n\n"
        "1️⃣ Faylni yuklab oling.\n"
        "2️⃣ Telegram ichida fayl ustiga bosing → <b>Share (Ulashish)</b> tugmasi.\n"
        "3️⃣ Ro'yxatdan <b>Minecraft</b> ni tanlang (ko'rinmasa «Files»ga saqlab, u yerdan oching).\n"
        "4️⃣ O'yin faylni import qiladi, so'ng dunyo sozlamalarida paketni yoqing.\n"
        "5️⃣ Addonlar uchun <b>Experimental</b> funksiyalarni yoqishni unutmang."
    ),
    "windows": (
        "💻 <b>Windows 10/11 (Bedrock Edition)</b>\n\n"
        "1️⃣ Faylni yuklab oling.\n"
        "2️⃣ Faylni <b>ikki marta bosing</b> — Minecraft Bedrock avtomatik ochilib, import qiladi.\n"
        "3️⃣ Dunyo sozlamalarida Behavior/Resource Pack ni yoqing.\n"
        "4️⃣ Addonlar uchun <b>Experimental</b> funksiyalarni yoqing.\n\n"
        "ℹ️ Qo'lda o'rnatish: <code>%LocalAppData%\\Packages\\Microsoft.MinecraftUWP_8wekyb3d8bbwe\\LocalState\\games\\com.mojang</code> "
        "papkasidagi mos papkalarga joylang."
    ),
}


def guide_text(os_key: str) -> str:
    text = GUIDE[os_key]
    if config.guide_video_url:
        text += f"\n\n🎬 Video qo'llanma: {html.escape(config.guide_video_url)}"
    return text


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def card_caption(mod) -> str:
    desc = esc(mod.description)
    if len(desc) > 600:
        desc = desc[:600].rstrip() + "…"
    parts = [
        f"<b>{esc(mod.title)}</b>",
        "",
        desc,
        "",
        f"🎮 <b>Versiya:</b> {esc(mod.version)}",
        f"📂 <b>Bo'lim:</b> {CATEGORIES.get(mod.category, mod.category)}",
        f"📥 <b>Yuklashlar:</b> {mod.downloads}",
    ]
    if mod.tags:
        parts += ["", esc(mod.tags)]
    return "\n".join(parts)


def normalize_tags(raw: str) -> str:
    if raw.strip() in ("-", ""):
        return ""
    words = raw.replace(",", " ").split()
    return " ".join(w if w.startswith("#") else "#" + w for w in words)
