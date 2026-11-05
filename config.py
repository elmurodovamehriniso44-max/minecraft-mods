"""Bot sozlamalari. Barcha maxfiy qiymatlar muhit o'zgaruvchilaridan (Render > Environment) o'qiladi."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv ixtiyoriy
    pass

BASE_DIR = Path(__file__).resolve().parent


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int_list(raw: str) -> list[int]:
    result = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            result.append(int(part))
    return result


# --- Telegram ---------------------------------------------------------------
BOT_TOKEN = _env("BOT_TOKEN")
ADMIN_IDS = _int_list(_env("ADMIN_IDS"))  # masalan: 123456789,987654321

# Majburiy obuna kanali: "@kanal_username" yoki -100... ko'rinishidagi ID.
# Bo'sh qoldirilsa, obuna tekshiruvi o'chiriladi. Bot kanalda ADMIN bo'lishi shart!
REQUIRED_CHANNEL = _env("REQUIRED_CHANNEL")
CHANNEL_LINK = _env("REQUIRED_CHANNEL_LINK") or (
    f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}" if REQUIRED_CHANNEL.startswith("@") else ""
)

# --- Spotify ----------------------------------------------------------------
SPOTIFY_CLIENT_ID = _env("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = _env("SPOTIFY_CLIENT_SECRET")

# --- Papkalar va baza -------------------------------------------------------
# Render'da bazani saqlab qolish uchun Persistent Disk ulang va DATA_DIR=/var/data qiling.
DATA_DIR = Path(_env("DATA_DIR") or str(BASE_DIR / "data"))
DOWNLOAD_DIR = DATA_DIR / "downloads"
DB_PATH = DATA_DIR / "bot.db"

# --- yt-dlp -----------------------------------------------------------------
COOKIES_CANDIDATES = [p for p in (
    Path(_env("COOKIES_FILE")) if _env("COOKIES_FILE") else None,
    Path("/etc/secrets/cookies.txt"),   # Render "Secret Files"
    BASE_DIR / "cookies.txt",
) if p]
COOKIES_RUNTIME = DATA_DIR / "cookies_runtime.txt"  # yt-dlp yozishi mumkin, shuning uchun nusxa ishlatiladi

PLAYER_CLIENTS = [c.strip() for c in _env("YT_PLAYER_CLIENTS", "android_vr,web_embedded,android,web,ios").split(",") if c.strip()]
PROXY_URL = _env("PROXY_URL")   # masalan: http://user:pass@host:port (YouTube bloklasa — rezident proksi)
AUDIO_QUALITY = _env("AUDIO_QUALITY", "128")        # MP3 bitrate (kbps): past = tezroq va yengilroq
MAX_FILE_MB = int(_env("MAX_FILE_MB", "49"))        # Bot API limiti: 50 MB
MAX_DURATION = int(_env("MAX_DURATION", "1200"))    # soniya (20 daqiqadan uzun videolar o'tkazib yuboriladi)
MAX_PARALLEL_DOWNLOADS = int(_env("MAX_PARALLEL_DOWNLOADS", "2"))
ALBUM_MAX_TRACKS = int(_env("ALBUM_MAX_TRACKS", "15"))

# --- Render web-servis porti (health-check uchun) ---------------------------
PORT = int(_env("PORT", "10000"))

# --- Menyu tugmalari --------------------------------------------------------
BTN_SEARCH = "🔍 Qo'shiq qidirish"
BTN_TOP = "🔥 Top musiqalar"
BTN_ADMIN = "⚙️ Admin panel"


def validate() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN o'rnatilmagan! Render > Environment bo'limiga qo'shing.")
