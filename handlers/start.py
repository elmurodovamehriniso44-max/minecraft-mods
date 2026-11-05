import html

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

import config
from handlers.music import deliver_by_key
from services import utils

router = Router()

WELCOME = (
    "👋 <b>Salom, {name}!</b>\n\n"
    "🎵 Men qo'shiqni <b>havoladan</b> ham, <b>nomidan</b> ham topaman.\n\n"
    "🔗 Instagram Reels, TikTok, YouTube Shorts yoki istalgan video havolasini yuboring — "
    "videodagi qo'shiqni aniqlab, to'liq MP3 qilib beraman.\n"
    "🔍 Yoki qo'shiq/ijrochi nomini yozing.\n\n"
    "💡 Guruhda: <code>@{username} qo'shiq nomi</code>"
)
HELP = (
    "ℹ️ <b>Yordam</b>\n\n"
    "1️⃣ Video havolasini yuboring → bot qo'shiqni aniqlaydi va to'liq MP3 yuboradi\n"
    "2️⃣ Qo'shiq nomini yozing → natijalardan birini tanlang (◀️ ▶️ bilan sahifalang)\n"
    "3️⃣ ⚡ belgisi — qo'shiq tayyor, bir zumda yuboriladi\n"
    "4️⃣ 🔥 Top musiqalar — eng ko'p tinglanganlar\n\n"
    "👥 Guruhlarda: <code>@{username} qo'shiq nomi</code>"
)


async def send_welcome(message: Message, bot: Bot, user=None) -> None:
    user = user or message.from_user
    me = await bot.me()
    await message.answer(
        WELCOME.format(name=html.escape(user.full_name), username=me.username),
        reply_markup=utils.main_menu(user.id in config.ADMIN_IDS),
    )


@router.message(CommandStart(deep_link=True))
async def start_deeplink(message: Message, command: CommandObject, bot: Bot) -> None:
    arg = command.args or ""
    if arg.startswith("dl_"):
        await deliver_by_key(bot, message.chat.id, arg[3:])
        return
    await send_welcome(message, bot)


@router.message(CommandStart())
async def start(message: Message, bot: Bot) -> None:
    await send_welcome(message, bot)


@router.callback_query(F.data == "check_sub")
async def check_sub(cb: CallbackQuery, bot: Bot) -> None:
    if await utils.is_subscribed(bot, cb.from_user.id, force=True):
        await cb.answer("✅ Rahmat! Endi foydalanishingiz mumkin.")
        if cb.message:
            try:
                await cb.message.delete()
            except Exception:
                pass
            await send_welcome(cb.message, bot, user=cb.from_user)
    else:
        await cb.answer("❌ Siz hali obuna bo'lmadingiz.", show_alert=True)


@router.message(Command("help"))
@router.message(F.text == utils.BTN_HELP)
async def help_cmd(message: Message, bot: Bot) -> None:
    me = await bot.me()
    await message.answer(HELP.format(username=me.username))


@router.message(F.text == utils.BTN_SEARCH)
async def search_prompt(message: Message) -> None:
    await message.answer("🔍 Qo'shiq nomini yozing yoki Instagram/TikTok/YouTube havolasini yuboring:")
