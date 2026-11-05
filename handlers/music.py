import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.downloader import search_youtube_tracks, download_audio_by_url
from services.db import get_cached_track, save_track_cache
from config import WORKDIR

router = Router()

@router.message(F.text)
async def handle_music_search(message: Message):
    text = message.text.strip()
    
    # 1. Keshdan tekshirish
    cached = get_cached_track(text)
    if cached:
        file_id, title, performer = cached
        await message.answer_audio(audio=file_id, caption=f"🎵 {performer} - {title}\n🤖 @{message.bot.username}")
        return

    status_msg = await message.reply("🔍 Qo'shiqlar va variantlar qidirilmoqda...")

    # 2. 24 tagacha variantni qidirish
    results = search_youtube_tracks(text, limit=24)
    
    if not results:
        await status_msg.edit_text("❌ Hech narsa topilmadi. Qayta yozib ko'ring.")
        return

    # 3. Natijalarni inline tugmalarga joylash
    builder = InlineKeyboardBuilder()
    for item in results:
        title = item.get('title', 'Nomaʼlum trek')
        video_id = item.get('id')
        
        # Tugma matni juda uzun bo'lib ketmasligi uchun qisqartiramiz
        display_title = title[:45] + "..." if len(title) > 45 else title
        builder.row(InlineKeyboardButton(text=f"🎵 {display_title}", callback_data=f"dl_{video_id}"))

    builder.adjust(1) # Har bir qatorda 1 tadan tugma

    await status_msg.edit_text(
        f"🔎 **\"{text}\"** bo'yicha topilgan variantlar:\nKerakli qo'shiqni tanlang:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# 4. Foydalanuvchi tugmani bosganda ishlaydigan handler
@router.callback_query(F.data.startswith("dl_"))
async def process_track_download(callback: CallbackQuery):
    video_id = callback.data.split("_")[1]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    await callback.message.edit_text("📥 Tanlangan qo'shiq yuklab olinmoqda...")
    
    mp3_path, title, performer = download_audio_by_url(url, WORKDIR)
    
    if not mp3_path or not os.path.exists(mp3_path):
        await callback.message.edit_text("❌ Yuklab olishda xatolik yuz berdi. Qayta urinib ko'ring.")
        return

    await callback.message.edit_text("📤 Fayl Telegramga yuborilmoqda...")
    
    try:
        audio_file = FSInputFile(mp3_path)
        sent_msg = await callback.message.answer_audio(
            audio=audio_file, 
            caption=f"🎶 {title}\n🤖 @{callback.bot.username}"
        )
        
        # File_ID ni keshga saqlaymiz
        if sent_msg.audio:
            save_track_cache(video_id, sent_msg.audio.file_id, title, performer)
            
        await callback.message.delete()
    except Exception as e:
        await callback.message.edit_text(f"❌ Yuborishda xatolik: {e}")
    finally:
        if os.path.exists(mp3_path):
            try:
                os.remove(mp3_path)
            except:
                pass