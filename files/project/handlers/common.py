"""/start, bosh menyu, yordam, bekor qilish."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import inline as K
from utils import texts as T
from utils.helpers import is_admin, safe_edit

router = Router(name="common")


def _menu_kb(user_id: int):
    return K.main_menu_kb(is_admin(user_id))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    await message.answer(T.welcome(user.full_name), reply_markup=_menu_kb(user.id))


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(T.MAIN_MENU, reply_markup=_menu_kb(message.from_user.id))


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await message.answer(T.HELP, reply_markup=K.menu_only_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(T.CANCELLED, reply_markup=_menu_kb(message.from_user.id))


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(cb, T.MAIN_MENU, _menu_kb(cb.from_user.id))
    await cb.answer()


@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await safe_edit(cb, T.HELP, K.menu_only_kb())
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()
