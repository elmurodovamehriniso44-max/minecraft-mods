import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int_list(value: str) -> list[int]:
    out: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = _int_list(os.getenv("ADMIN_IDS", ""))
CHANNELS = ["@" + c.strip().lstrip("@") for c in os.getenv("CHANNELS", "").split(",") if c.strip()]

_storage = os.getenv("STORAGE_CHAT_ID", "").strip()
STORAGE_CHAT_ID = int(_storage) if _storage.lstrip("-").isdigit() else (ADMIN_IDS[0] if ADMIN_IDS else 0)

DB_PATH = os.getenv("DB_PATH", "data/bot.db")
TMP_DIR = Path(os.getenv("TMP_DIR", "/tmp/linkshazam"))
TMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_PARALLEL = int(os.getenv("MAX_PARALLEL", "2"))
MAX_TRACK_SECONDS = 720      # yuboriladigan trek maksimal davomiyligi
MAX_LINK_SECONDS = 900       # havoladagi video maksimal davomiyligi
MAX_FILE_BYTES = 49 * 1024 * 1024  # Bot API yuklash limiti ~50 MB

PROXY = os.getenv("PROXY", "").strip() or None

# Render "Secret Files" faqat o'qish uchun bo'ladi, yt-dlp esa cookie faylga yozishga urinadi.
# Shuning uchun nusxasini yozish mumkin bo'lgan joyga ko'chiramiz.
COOKIES_FILE = None
_src = os.getenv("COOKIES_FILE", "").strip()
if _src and Path(_src).is_file():
    _dst = TMP_DIR / "cookies.txt"
    shutil.copyfile(_src, _dst)
    COOKIES_FILE = str(_dst)
