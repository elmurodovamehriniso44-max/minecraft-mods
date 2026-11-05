"""Yordamchi funksiyalar."""
import logging
import re
from pathlib import Path

import aiohttp
from aiogram import Bot

log = logging.getLogger(__name__)


def normalize_key(text: str) -> str:
    """Qidiruv/kesh kaliti: kichik harf, belgilarsiz."""
    return re.sub(r"[\W_]+", " ", (text or "").casefold()).strip()


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name).strip(" .")
    return (name or "audio")[:max_len]


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fmt_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"


async def download_bytes(url: str, timeout: int = 15) -> bytes | None:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:  # tarmoq xatolari muhim emas, muqova ixtiyoriy
        log.warning("Muqovani yuklab bo'lmadi: %s", e)
    return None


def safe_unlink(path: Path | None) -> None:
    try:
        if path:
            Path(path).unlink(missing_ok=True)
    except OSError:
        pass


async def bot_caption(bot: Bot) -> str:
    me = await bot.me()
    return f"🎧 @{me.username}"
