import asyncio
import contextlib
import html
import logging
import math
import os
import re
import secrets
import shutil
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config

logger = logging.getLogger(__name__)

esc = html.escape
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
KEY_RE = re.compile(r"^[\w-]{1,40}$")
YT_ID_RE = re.compile(r"^[\w-]{11}$")


# ---------------- URL ----------------
def extract_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,;!?") if m else None


def normalize_url(url: str) -> str:
    """Kesh kaliti uchun: tracking parametrlari (igsh, utm...) tashlab yuboriladi."""
    p = urlsplit(url.strip())
    host = p.netloc.lower()
    query = "" if host.endswith(("instagram.com", "tiktok.com")) else p.query
    return urlunsplit((p.scheme.lower(), host, p.path.rstrip("/") or "/", query, ""))


# ---------------- fayl tizimi / ffmpeg ----------------
def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def make_workdir() -> str:
    config.WORKDIR.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix="job_", dir=config.WORKDIR)


def rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


@contextlib.contextmanager
def tempdir():
    path = make_workdir()
    try:
        yield path
    finally:
        rmtree(path)


def cleanup_workdir(max_age: int = 3600) -> None:
    """Bot qulab qolganda yetim qolgan vaqtinchalik papkalarni tozalaydi."""
    config.WORKDIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for p in config.WORKDIR.iterdir():
        try:
            if p.is_dir() and now - p.stat().st_mtime > max_age:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


async def run_ffmpeg(args: list[str], timeout: int = 90) -> None:
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg topilmadi (Dockerfile orqali o'rnating)")
    proc = await asyncio.create_subprocess_exec(
        exe, "-hide_banner", "-loglevel", "error", "-y", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        raise RuntimeError(err.decode(errors="ignore")[-300:])


async def fetch_bytes(url: str | None, max_bytes: int = 5_000_000) -> bytes | None:
    if not url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    data = await r.content.read(max_bytes)
                    return data or None
    except Exception:
        logger.debug("fetch_bytes xatolik: %s", url, exc_info=True)
    return None


def fmt_duration(sec: int | None) -> str:
    if not sec:
        return ""
    return f"{sec // 60}:{sec % 60:02d}"


async def safe_edit(msg: Message | None, text: str) -> None:
    if not msg:
        return
    try:
        await msg.edit_text(text)
    except TelegramBadRequest:
        pass
    except Exception:
        logger.debug("safe_edit xatolik", exc_info=True)


# ---------------- qidiruv natijalari (pagination uchun xotira) ----------------
class ResultStore:
    def __init__(self, ttl: int = 1800, maxsize: int = 2000) -> None:
        self._d: dict[str, tuple[float, list]] = {}
        self._ttl, self._max = ttl, maxsize

    def put(self, items: list) -> str:
        now = time.time()
        if len(self._d) >= self._max:
            self._d = {k: v for k, v in self._d.items() if now - v[0] < self._ttl}
            if len(self._d) >= self._max:
                self._d.clear()
        token = secrets.token_urlsafe(4)[:6]
        self._d[token] = (now, items)
        return token

    def get(self, token: str) -> list | None:
        hit = self._d.get(token)
        if hit and time.time() - hit[0] < self._ttl:
            return hit[1]
        return None


STORE = ResultStore()


# ---------------- tugmalar ----------------
BTN_SEARCH = "🔍 Qo'shiq qidirish"
BTN_TOP = "🔥 Top musiqalar"
BTN_ADMIN = "⚙️ Admin panel"
BTN_HELP = "ℹ️ Yordam"


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=BTN_SEARCH), KeyboardButton(text=BTN_TOP)]]
    last = [KeyboardButton(text=BTN_HELP)]
    if is_admin:
        last.append(KeyboardButton(text=BTN_ADMIN))
    rows.append(last)
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Qo'shiq nomi yoki havola yuboring...",
    )


def paginate_kb(items: list[tuple], page: int, nav_cb, page_size: int = config.PAGE_SIZE) -> InlineKeyboardMarkup:
    """items: (key, artist, title, cached). nav_cb(page) -> callback_data."""
    pages = max(1, math.ceil(len(items) / page_size))
    page = max(0, min(page, pages - 1))
    b = InlineKeyboardBuilder()
    for key, artist, title, cached in items[page * page_size : (page + 1) * page_size]:
        label = f"{'⚡' if cached else '🎵'} {artist} - {title}"
        b.button(text=label[:57] + "..." if len(label) > 60 else label, callback_data=f"dl:{key}")
    b.adjust(1)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=nav_cb(page - 1)))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=nav_cb(page + 1)))
        b.row(*nav)
    return b.as_markup()


def subscribe_kb() -> InlineKeyboardMarkup:
    rows = []
    if config.CHANNEL_URL:
        rows.append([InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=config.CHANNEL_URL)])
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistika", callback_data="adm:stat")],
            [InlineKeyboardButton(text="📣 Broadcast yo'riqnomasi", callback_data="adm:bc")],
        ]
    )


# ---------------- majburiy obuna ----------------
_sub_ok_until: dict[int, float] = {}


async def is_subscribed(bot: Bot, user_id: int, force: bool = False) -> bool:
    if not config.CHANNEL_ID or user_id in config.ADMIN_IDS:
        return True
    now = time.monotonic()
    if not force and _sub_ok_until.get(user_id, 0) > now:
        return True
    try:
        m = await bot.get_chat_member(config.CHANNEL_ID, user_id)
    except TelegramAPIError as e:
        # Bot kanalda admin emas / kanal noto'g'ri: foydalanuvchilarni bloklab qo'ymaymiz
        logger.warning("Obunani tekshirib bo'lmadi: %s", e)
        return True
    ok = m.status in (
        ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR
    ) or (m.status == ChatMemberStatus.RESTRICTED and getattr(m, "is_member", False))
    if ok:
        _sub_ok_until[user_id] = now + 300
    else:
        _sub_ok_until.pop(user_id, None)
    return ok
