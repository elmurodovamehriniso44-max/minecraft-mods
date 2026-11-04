from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_SEARCH = "🔎 Qo'shiq qidirish"
BTN_TOP = "🔥 Top musiqalar"
BTN_LINK = "🔗 Havoladan topish"
BTN_HELP = "ℹ️ Yordam"
BTN_ADMIN = "⚙️ Admin panel"


def main_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_SEARCH), KeyboardButton(text=BTN_TOP)],
        [KeyboardButton(text=BTN_LINK), KeyboardButton(text=BTN_HELP)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(
        keyboard=rows, resize_keyboard=True, input_field_placeholder="Qo'shiq nomi yoki havola yuboring..."
    )
