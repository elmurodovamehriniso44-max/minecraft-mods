import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _ids(value: str) -> list[int]:
    return [int(x) for x in value.replace(" ", "").split(",") if x.lstrip("-").isdigit()]


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------- Telegram ----------
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. .env faylga yoki Render Environment'ga qo'shing.")

ADMIN_IDS: list[int] = _ids(os.getenv("ADMIN_IDS", ""))

# Majburiy obuna kanali: "@kanal" yoki "-100123456789". Bo'sh bo'lsa tekshiruv o'chadi.
_raw_channel = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID = int(_raw_channel) if _raw_channel.lstrip("-").isdigit() else _raw_channel
CHANNEL_URL: str = os.getenv("CHANNEL_URL", "").strip() or (
    f"https://t.me/{_raw_channel.lstrip('@')}" if _raw_channel.startswith("@") else ""
)

# ---------- Yo'llar ----------
WORKDIR: Path = Path(os.getenv("WORKDIR", str(BASE_DIR / "workdir")))
DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "bot.db"))
PORT: int = int(os.getenv("PORT", "10000"))


def _find_cookies() -> str:
    """cookies.txt: COOKIES_FILE env -> Render Secret File -> loyiha papkasi."""
    for p in (os.getenv("COOKIES_FILE", ""), "/etc/secrets/cookies.txt", str(BASE_DIR / "cookies.txt")):
        if p and os.path.isfile(p):
            return p
    return ""


COOKIES_FILE: str = _find_cookies()

# YouTube player_client profillari (tartib bilan sinab ko'riladi)
YT_PLAYER_CLIENTS: list[str] = [
    c.strip() for c in os.getenv("YT_PLAYER_CLIENTS", "").split(",") if c.strip()
] or (["web", "android", "ios"] if COOKIES_FILE else ["android", "web", "ios"])

# ---------- Limitlar ----------
LINK_MAX_DURATION: int = int(os.getenv("LINK_MAX_DURATION", "900"))    # havoladagi video (sek)
TRACK_MAX_DURATION: int = int(os.getenv("TRACK_MAX_DURATION", "900"))  # to'liq qo'shiq (sek)
TRACK_MIN_DURATION: int = int(os.getenv("TRACK_MIN_DURATION", "45"))
MAX_PARALLEL_JOBS: int = int(os.getenv("MAX_PARALLEL_JOBS", "2"))
MAX_FILE_BYTES: int = 49 * 1024 * 1024
MP3_BITRATE: str = os.getenv("MP3_BITRATE", "192")

PAGE_SIZE: int = 5
SEARCH_LIMIT: int = 15

# Faqat tinglash uchun: Telegram saqlash/forward qilishni cheklaydi
PROTECT_CONTENT: bool = _bool("PROTECT_CONTENT", "true")
