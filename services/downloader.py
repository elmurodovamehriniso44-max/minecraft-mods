import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
from config import WORKDIR, SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET

# Spotify sozlamalari
sp = None
if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
    try:
        auth_manager = SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        print(f"Spotify ulanishida xatolik: {e}")

def resolve_spotify_link(url: str):
    """Spotify havolasidan Artist - Track formatini oladi"""
    if not sp:
        return None
    try:
        if "track" in url:
            track_info = sp.track(url)
            name = track_info['name']
            artists = ", ".join([artist['name'] for artist in track_info['artists']])
            return f"{artists} - {name}"
    except Exception as e:
        print(f"Spotify resolve xatosi: {e}")
    return None

def search_youtube_tracks(query: str, limit: int = 24):
    """YouTube'dan ko'pi bilan 'limit' ta (24 tagacha) qidiruv natijasini oladi"""
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'noplaylist': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web', 'ios']}}
    }
    
    # Spotify havolasi bo'lsa avval matnga o'giramiz
    target_query = query
    if "spotify.com" in query:
        resolved = resolve_spotify_link(query)
        if resolved:
            target_query = resolved

    search_target = f"ytsearch{limit}:{target_query}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=False)
            if 'entries' in info:
                return info['entries']
    except Exception as e:
        print(f"Qidiruvda xatolik: {e}")
    return []

def download_audio_by_url(url: str, output_path: str = WORKDIR):
    """Tanlangan aniq video/audio havolasi yoki ID orqali MP3 yuklab oladi"""
    os.makedirs(output_path, exist_ok=True)
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
        'extractor_args': {'youtube': {'player_client': ['android', 'web', 'ios']}}
    }
    
    if os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_file = os.path.splitext(filename)[0] + ".mp3"
            if os.path.exists(mp3_file):
                return mp3_file, info.get('title', 'Audio'), info.get('uploader', 'Artist')
    except Exception as e:
        print(f"Yuklab olishda xatolik: {e}")
        
    return None, None, None