from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from services.subscription import get_unsubscribed

router = Router()

WELCOME = (
    "👋 <b>Salom, {name}!</b>\n\n"
    "Men musiqa topuvchi botman:\n"
    "🔗 Instagram / TikTok / YouTube havolasini yuboring — videodagi qo'shiqni aniqlayman\n"
    "✍️ Qo'shiq yoki ijrochi nomini yozing — qidirib beraman\n"
    "👥 Istalgan chatda <code>@{bot} qo'shiq nomi</code> deb yozing"
)

HELP = (
    "ℹ️ <b>Yordam</b>\n\n"
    "1. Video havolasini yuboring → qo'shiq nomi + MP3.\n"
    "2. Matn yozing → natijalar tugmalarda chiqadi.\n"
    "3. Guruhda: <code>@{bot} nom</code>.\n\n"
    "Yopiq (private) videolarni yuklab bo'lmaydi."
)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Qo'shiq qidirish", switch_inline_query_current_chat="")],
            [InlineKeyboardButton(text="👥 Guruhda ishlatish", switch_inline_query="")],
            [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    me = await message.bot.me()
    await message.answer(
        WELCOME.format(name=message.from_user.full_name, bot=me.username), reply_markup=main_menu()
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    me = await message.bot.me()
    await message.answer(HELP.format(bot=me.username), reply_markup=main_menu())


@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery):
    me = await cb.bot.me()
    await cb.answer()
    if cb.message:
        await cb.message.answer(HELP.format(bot=me.username), reply_markup=main_menu())


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    missing = await get_unsubscribed(cb.bot, cb.from_user.id)
    if missing:
        await cb.answer("Hali hamma kanalga obuna bo'lmadingiz ❌", show_alert=True)
        return
    await cb.answer("✅ Rahmat!")
    me = await cb.bot.me()
    if cb.message:
        try:
            await cb.message.delete()
        except Exception:
            pass
    await cb.bot.send_message(
        cb.from_user.id,
        WELCOME.format(name=cb.from_user.full_name, bot=me.username),
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer("⏳ Yuklanmoqda, biroz kuting...")
