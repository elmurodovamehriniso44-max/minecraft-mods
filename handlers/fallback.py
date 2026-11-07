"""Boshqa hech qaysi handler ushlamagan hodisalar."""
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import inline as K
from utils import texts as T
from utils.helpers import is_admin

router = Router(name="fallback")


@router.callback_query()
async def unknown_callback(cb: CallbackQuery) -> None:
    if cb.data and cb.data.startswith("adm:"):
        await cb.answer(T.NO_PERMISSION, show_alert=True)
    else:
        await cb.answer(T.STALE_BUTTON, show_alert=True)


@router.message()
async def unknown_message(message: Message, state: FSMContext) -> None:
    if message.text and message.text.startswith("/admin"):
        await message.answer(T.NO_PERMISSION)
        return
    await message.answer(T.USE_MENU, reply_markup=K.main_menu_kb(is_admin(message.from_user.id)))
