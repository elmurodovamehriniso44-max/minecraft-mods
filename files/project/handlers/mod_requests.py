"""Foydalanuvchilarning mod so'rovlari."""
import logging
import re
from difflib import SequenceMatcher

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import queries as q
from keyboards import inline as K
from keyboards import admin as AK
from states.states import RequestState
from utils import texts as T
from utils.filters import PlainText
from utils.helpers import is_admin, normalize_text, safe_edit

log = logging.getLogger(__name__)
router = Router(name="mod_requests")

_LINK_RE = re.compile(r"(https?://|www\.|t\.me/|@\w{4,}|\b\w+\.(com|ru|uz|org|net|me|io)\b)", re.IGNORECASE)


@router.callback_query(F.data == "req")
async def cb_request_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    mine = await q.list_user_requests(cb.from_user.id, 5)
    await safe_edit(cb, T.request_menu(mine), K.request_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "reqnew")
async def cb_request_new(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RequestState.text)
    await safe_edit(cb, T.REQUEST_ASK, K.request_cancel_kb())
    await cb.answer()


async def _is_duplicate(normalized: str) -> bool:
    if await q.find_exact_duplicate(normalized):
        return True
    for other in await q.recent_normalized(100):
        if SequenceMatcher(None, normalized, other).ratio() >= 0.9:
            return True
    return False


@router.message(RequestState.text, PlainText())
async def on_request_text(message: Message, state: FSMContext) -> None:
    text = " ".join(message.text.split())
    user = message.from_user

    if not 5 <= len(text) <= 300:
        await message.answer(T.REQUEST_BAD_LENGTH)
        return
    if _LINK_RE.search(text):
        await message.answer(T.REQUEST_LINKS)
        return

    if await q.count_user_requests_since(user.id, "-1 day") >= config.REQUEST_DAILY_LIMIT:
        await state.clear()
        await message.answer(T.REQUEST_DAILY_LIMIT, reply_markup=K.main_menu_kb(is_admin(user.id)))
        return
    if await q.count_user_requests_since(user.id, "-1 minute") >= 1:
        await message.answer(T.REQUEST_TOO_FAST)
        return

    normalized = normalize_text(text)
    if len(normalized) < 3:
        await message.answer(T.REQUEST_BAD_LENGTH)
        return
    if await _is_duplicate(normalized):
        await state.clear()
        await message.answer(T.REQUEST_DUPLICATE, reply_markup=K.main_menu_kb(is_admin(user.id)))
        return

    req_id = await q.add_request(user.id, text, normalized)
    await state.clear()
    await message.answer(T.REQUEST_SENT, reply_markup=K.main_menu_kb(is_admin(user.id)))

    # Adminlarga bildirishnoma
    for admin_id in config.ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                T.request_notify_admin(req_id, user, text),
                reply_markup=AK.markup([[AK.btn("📨 Ko'rish", f"adm:rv:{req_id}:pending:0")]]),
            )
        except TelegramAPIError as exc:
            log.warning("Adminga (%s) xabar yuborilmadi: %s", admin_id, exc)


@router.message(RequestState.text)
async def on_request_wrong_input(message: Message) -> None:
    await message.answer(T.NEED_TEXT)
