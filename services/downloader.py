import os
import yt_dlp

def download_audio(query_or_url: str, output_path: str = "downloads"):
    # Papka mavjud bo'lmasa yaratamiz
    os.makedirs(output_path, exist_ok=True)
    
    # yt-dlp sozlamalari
    cookies_path = "cookies.txt"
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(output_path, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
    }
    
    # Agar cookies.txt fayli mavjud bo'lsa, uni qo'shamiz
    if os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path

    # Agar havola bo'lmasa, uni avtomatik ravishda SoundCloud qidiruviga yo'naltiramiz
    search_target = query_or_url if query_or_url.startswith("http") else f"scsearch:{query_or_url}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            mp3_file = os.path.splitext(filename)[0] + ".mp3"
            return mp3_file
    except Exception as e:
        print(f"Yuklab olishda xatolik: {e}")
        return None