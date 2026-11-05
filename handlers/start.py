"""/start, menyu va yordam."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)

import config

router = Router(name="start")

WELCOME = (
    "👋 <b>Salom, {name}!</b>\n\n"
    "Men Spotify havolalari va qo'shiq nomlari bo'yicha musiqa topib beraman 🎧\n\n"
    "• Spotify <b>trek</b> yoki <b>albom</b> havolasini yuboring\n"
    "• Yoki qo'shiq nomini yozing: <code>Artist - Qo'shiq</code>\n"
    "• Istalgan chatda: <code>@{bot} qo'shiq nomi</code>"
)

HELP = (
    "ℹ️ <b>Yordam</b>\n\n"
    "1️⃣ Spotify havolasini yuboring — trek yoki albom.\n"
    "2️⃣ Qo'shiq nomini yozing — natijalar tugmalar bilan chiqadi.\n"
    "3️⃣ Inline rejim: istalgan chatda <code>@{bot} nom</code> deb yozing.\n"
    "4️⃣ «🔥 Top musiqalar» — eng ko'p yuklanganlar.\n\n"
    "Muammo bo'lsa, boshqa nom bilan urinib ko'ring."
)


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=config.BTN_SEARCH), KeyboardButton(text=config.BTN_TOP)]]
    if is_admin:
        rows.append([KeyboardButton(text=config.BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _inline_search_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔎 Inline qidiruv", switch_inline_query_current_chat=""),
    ]])


@router.message(CommandStart())
async def cmd_start(message: Message):
    me = await message.bot.me()
    is_admin = message.from_user.id in config.ADMIN_IDS
    await message.answer(
        WELCOME.format(name=message.from_user.full_name, bot=me.username),
        reply_markup=main_menu(is_admin),
    )
    await message.answer("Pastdagi tugma orqali tez qidirishingiz mumkin 👇", reply_markup=_inline_search_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    me = await message.bot.me()
    await message.answer(HELP.format(bot=me.username))


@router.message(F.text == config.BTN_SEARCH)
async def btn_search(message: Message):
    await message.answer(
        "🎵 Qo'shiq nomini yoki Spotify havolasini yuboring.\n"
        "Masalan: <code>Imagine Dragons - Believer</code>",
        reply_markup=_inline_search_kb(),
    )


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery):
    # Bu yerga faqat obuna bo'lganlar yetib keladi (middleware tekshiradi)
    await call.answer("✅ Rahmat! Obuna tasdiqlandi.")
    if call.message:
        try:
            await call.message.delete()
        except Exception:
            pass
        me = await call.bot.me()
        await call.message.answer(
            WELCOME.format(name=call.from_user.full_name, bot=me.username),
            reply_markup=main_menu(call.from_user.id in config.ADMIN_IDS),
        )
