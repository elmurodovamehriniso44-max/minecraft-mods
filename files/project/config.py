"""Bot sozlamalari (.env fayldan o'qiladi)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _id_set(raw: str) -> set:
    result = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


def _str_list(name: str, default: str) -> list:
    raw = os.getenv(name, default) or default
    items = [p.strip() for p in raw.split(",") if p.strip()]
    return items or [p.strip() for p in default.split(",")]


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi! .env.example faylidan .env nusxa oling va tokenni kiriting."
    )

ADMIN_IDS = _id_set(os.getenv("ADMIN_IDS", ""))

_db_path = Path(os.getenv("DB_PATH", "data/bot.db"))
DB_PATH = _db_path if _db_path.is_absolute() else BASE_DIR / _db_path

# Fayl cheklovlari
MAX_FILE_SIZE = _int_env("MAX_FILE_MB", 100) * 1024 * 1024
ALLOWED_EXTENSIONS = {".mcaddon", ".mcpack", ".mcworld", ".zip"}

# Minecraft Bedrock versiyalari (admin panel va versiya filtri uchun)
MC_VERSIONS = _str_list("MC_VERSIONS", "1.21,1.20,1.19,1.18,1.17,1.16")

# Sahifalash
PAGE_SIZE = 8

# So'rovlar
REQUEST_DAILY_LIMIT = _int_env("REQUEST_DAILY_LIMIT", 3)
REQUEST_STATUSES = ("pending", "approved", "rejected", "completed")

# Rate limit: WINDOW soniyada COUNT tadan ko'p hodisa bo'lsa, bloklanadi
RATE_LIMIT_COUNT = 15
RATE_LIMIT_WINDOW = 10

# Kategoriyalar: (nomi, emoji)
CATEGORIES = [
    ("Qurollar", "⚔️"),
    ("Moblar", "👾"),
    ("Hayvonlar", "🐾"),
    ("Transport", "🚗"),
    ("Mebellar", "🛋"),
    ("Sehr", "✨"),
    ("Survival", "🏕"),
    ("Texnologiya", "⚙️"),
    ("Horror", "👻"),
    ("Dekoratsiya", "🎨"),
    ("Shaderlar", "🌅"),
    ("Xaritalar", "🗺"),
    ("Resource Packs", "🎒"),
    ("Boshqa", "📦"),
]
