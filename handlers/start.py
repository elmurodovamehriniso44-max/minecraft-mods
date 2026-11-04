from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from handlers import ui
from services.subscription import get_unsubscribed

router = Router()

WELCOME = (
    "👋 <b>Salom, {name}!</b>\n\n"
    "Men istalgan qo'shiqni topib beraman:\n\n"
    "✍️ <b>Nomini yozing</b> — qo'shiq yoki ijrochi nomi\n"
    "🔗 <b>Havola yuboring</b> — Instagram, TikTok, YouTube videosidagi qo'shiqni aniqlayman\n"
    "👥 <b>Guruhda</b> — <code>@{bot} qo'shiq nomi</code>\n\n"
    "Pastdagi menyudan foydalaning 👇"
)

HELP = (
    "ℹ️ <b>Yordam</b>\n\n"
    "1️⃣ Qo'shiq yoki ijrochi nomini yozing → natijalar ro'yxati chiqadi.\n"
    "2️⃣ Video havolasini yuboring → qo'shiq aniqlanib, MP3 yuboriladi.\n"
    "3️⃣ Istalgan chatda <code>@{bot} nom</code> deb yozing.\n"
    "4️⃣ «🔥 Top musiqalar» — hozirgi mashhur treklar.\n\n"
    "Yopiq (private) videolarni yuklab bo'lmaydi."
)


def _inline_row(me_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Shu yerda qidirish", switch_inline_query_current_chat="")],
            [InlineKeyboardButton(text="👥 Guruhga yuborish", switch_inline_query="")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    me = await message.bot.me()
    admin = message.from_user.id in config.ADMIN_IDS
    await message.answer(
        WELCOME.format(name=message.from_user.full_name, bot=me.username), reply_markup=ui.main_kb(admin)
    )


@router.message(Command("help"))
@router.message(F.text == ui.BTN_HELP)
async def cmd_help(message: Message):
    me = await message.bot.me()
    await message.answer(HELP.format(bot=me.username), reply_markup=_inline_row(me.username))


@router.message(F.text == ui.BTN_SEARCH)
async def btn_search(message: Message):
    await message.answer(
        "✍️ Qo'shiq yoki ijrochi nomini yozing.\nMasalan: <code>Konsta Yor-yor</code> yoki <code>Billie Eilish</code>"
    )


@router.message(F.text == ui.BTN_LINK)
async def btn_link(message: Message):
    await message.answer(
        "🔗 Instagram Reels, TikTok yoki YouTube Shorts havolasini yuboring — videodagi qo'shiqni topib beraman."
    )


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
        reply_markup=ui.main_kb(cb.from_user.id in config.ADMIN_IDS),
    )


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()
