"""Umumiy yordamchi funksiyalar."""
import html
import logging
import re
from typing import Callable, Optional

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import config

log = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def esc(value) -> str:
    """HTML uchun xavfsiz matn."""
    return html.escape(str(value if value is not None else ""), quote=False)


def trunc(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def fmt_size(size: Optional[int]) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.2f} GB"


def parse_versions(raw: Optional[str]) -> list:
    return [v for v in (raw or "").split(",") if v]


def join_versions(selected) -> str:
    """Tanlangan versiyalarni config tartibida vergul bilan birlashtiradi."""
    chosen = set(selected)
    ordered = [v for v in config.MC_VERSIONS if v in chosen]
    ordered += sorted(chosen - set(ordered))
    return ",".join(ordered)


def compat_state(mod_versions: Optional[str], user_version: Optional[str]) -> Optional[str]:
    """
    'unverified' — modda moslik ma'lumoti yo'q,
    None         — foydalanuvchi versiya tanlamagan,
    'ok' / 'no'  — mos / mos emas.
    """
    versions = parse_versions(mod_versions)
    if not versions:
        return "unverified"
    if not user_version:
        return None
    return "ok" if user_version in versions else "no"


_NORM_RE = re.compile(r"[\W_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    return _NORM_RE.sub(" ", (text or "").lower()).strip()


def fit_caption(builder: Callable[[int], str], limits=(500, 300, 150, 60, 0), max_len: int = 1000) -> str:
    """Telegram caption limiti (1024) ichiga sig'adigan matnni quradi."""
    text = ""
    for limit in limits:
        text = builder(limit)
        if len(text) <= max_len:
            return text
    return text


async def edit_ignore(coro) -> None:
    """'message is not modified' xatosini e'tiborsiz qoldiradi."""
    try:
        await coro
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def safe_edit(cb: CallbackQuery, text: str, kb: Optional[InlineKeyboardMarkup] = None) -> None:
    """
    Xabarni tahrirlaydi. Agar xabar rasm/fayl bo'lsa (matn yo'q) yoki
    eskirgan bo'lsa — o'chirib, yangisini yuboradi.
    """
    msg = cb.message
    if isinstance(msg, Message):
        if msg.text is not None:
            await edit_ignore(msg.edit_text(text, reply_markup=kb))
            return
        try:
            await msg.delete()
        except TelegramAPIError:
            pass
    await cb.bot.send_message(cb.from_user.id, text, reply_markup=kb)
