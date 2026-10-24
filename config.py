import hashlib
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: list
    database_url: str
    webhook_base: str | None
    port: int
    webhook_secret: str
    guide_video_url: str | None


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN o'rnatilmagan!")

    admin_ids = [
        int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()
    ]

    # Render avtomatik ravishda RENDER_EXTERNAL_URL beradi
    base = os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL")

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db"),
        webhook_base=base.rstrip("/") if base else None,
        port=int(os.getenv("PORT", "10000")),
        webhook_secret=hashlib.sha256(token.encode()).hexdigest()[:32],
        guide_video_url=os.getenv("GUIDE_VIDEO_URL") or None,
    )


config = load_config()
