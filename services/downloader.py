"""yt-dlp + ffmpeg: YouTube (cookies.txt + player_client profillari) va SoundCloud zaxira mexanizmi."""
import asyncio
import logging
import shutil
import threading
import uuid
from pathlib import Path

from yt_dlp import YoutubeDL

import config

log = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


_BAD_WORDS = (
    "live", "cover", "karaoke", "remix", "reaction", "slowed", "sped up", "speed up",
    "nightcore", "8d", "instrumental", "tutorial", "mashup",
)

_sem: asyncio.Semaphore | None = None
_cookie_lock = threading.Lock()
_cookie_state: dict = {"resolved": False, "path": None}


# --- Yordamchilar -----------------------------------------------------------
def _prepare_cookies() -> str | None:
    """cookies.txt ni topadi va yozish mumkin bo'lgan joyga nusxalaydi (Render Secret Files read-only)."""
    with _cookie_lock:
        if _cookie_state["resolved"]:
            return _cookie_state["path"]
        _cookie_state["resolved"] = True
        for src in config.COOKIES_CANDIDATES:
            try:
                if src.is_file() and src.stat().st_size > 0:
                    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, config.COOKIES_RUNTIME)
                    _cookie_state["path"] = str(config.COOKIES_RUNTIME)
                    log.info("cookies.txt topildi: %s", src)
                    break
            except OSError as e:
                log.warning("cookies.txt o'qilmadi (%s): %s", src, e)
        else:
            log.info("cookies.txt topilmadi — cookies'siz ishlaydi")
        return _cookie_state["path"]


def _ffmpeg_location() -> str | None:
    if shutil.which("ffmpeg"):
        return None
    try:  # zaxira: imageio-ffmpeg paketidagi binar
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _base_opts(cookies: str | None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "geo_bypass": True,
    }
    if cookies:
        opts["cookiefile"] = cookies
    ff = _ffmpeg_location()
    if ff:
        opts["ffmpeg_location"] = ff
    return opts


def _score(entry: dict, query_l: str, target: int | None) -> float:
    """Past ball = yaxshiroq nomzod."""
    title = (entry.get("title") or "").lower()
    channel = (entry.get("channel") or entry.get("uploader") or "").lower()
    score = 0.0
    dur = entry.get("duration")
    if target and dur:
        score += min(abs(dur - target), 120)
    elif not dur:
        score += 30
    for w in _BAD_WORDS:
        if w in title and w not in query_l:
            score += 60
    if channel.endswith("- topic"):
        score -= 40
    if "official audio" in title:
        score -= 15
    return score


def _search(prefix: str, query: str, cookies: str | None, target: int | None, n: int = 6) -> list[str]:
    opts = {**_base_opts(cookies), "extract_flat": True, "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{prefix}{n}:{query}", download=False)
    q = query.lower()
    cands = []
    for e in (info or {}).get("entries") or []:
        if not e:
            continue
        dur = e.get("duration")
        if dur and (dur > config.MAX_DURATION or dur < 30):  # uzun mikslar va 30s preview'lar
            continue
        url = e.get("url") or ""
        if not url.startswith("http"):
            if e.get("id") and prefix == "ytsearch":
                url = f"https://www.youtube.com/watch?v={e['id']}"
            else:
                continue
        cands.append((_score(e, q, target), url))
    cands.sort(key=lambda x: x[0])
    return [u for _, u in cands]


def _cleanup(stem: str) -> None:
    for p in config.DOWNLOAD_DIR.glob(f"{stem}*"):
        try:
            p.unlink()
        except OSError:
            pass


def _fetch(url: str, client: str | None, cookies: str | None) -> Path:
    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:12]
    opts = {
        **_base_opts(cookies),
        "format": "bestaudio/best",
        "outtmpl": str(config.DOWNLOAD_DIR / f"{stem}.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
    }
    if client:
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        mp3 = config.DOWNLOAD_DIR / f"{stem}.mp3"
        if not mp3.exists():
            raise DownloadError("MP3 fayl hosil bo'lmadi (ffmpeg o'rnatilganmi?)")
        if mp3.stat().st_size > config.MAX_FILE_MB * 1024 * 1024:
            raise DownloadError(f"Fayl {config.MAX_FILE_MB} MB dan katta")
        return mp3
    except Exception:
        _cleanup(stem)
        raise


def _download_sync(query: str, duration_hint: int | None) -> Path:
    cookies = _prepare_cookies()
    errors: list[str] = []

    # 1) YouTube: har bir nomzod uchun player_client profillari ketma-ket sinab ko'riladi
    try:
        yt_cands = _search("ytsearch", query, cookies, duration_hint)
    except Exception as e:
        errors.append(f"YT qidiruv: {e}")
        yt_cands = []
    clients: list[str | None] = [*config.PLAYER_CLIENTS, None]  # None = yt-dlp standarti
    for url in yt_cands[:2]:
        for client in clients:
            try:
                return _fetch(url, client, cookies)
            except Exception as e:
                errors.append(f"YT[{client or 'default'}]: {str(e)[:150]}")
                log.warning("YouTube yuklash xatosi (%s, %s): %s", client, url, e)

    # 2) SoundCloud zaxira (YouTube cookies kerak emas)
    try:
        sc_cands = _search("scsearch", query, None, duration_hint)
    except Exception as e:
        errors.append(f"SC qidiruv: {e}")
        sc_cands = []
    for url in sc_cands[:3]:
        try:
            return _fetch(url, None, None)
        except Exception as e:
            errors.append(f"SC: {str(e)[:150]}")
            log.warning("SoundCloud yuklash xatosi (%s): %s", url, e)

    raise DownloadError(" | ".join(errors[-4:]) or "Hech narsa topilmadi")


async def download_audio(query: str, duration_hint: int | None = None) -> Path:
    """Qidiradi va MP3 qilib yuklaydi. Parallel yuklashlar soni cheklangan."""
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(config.MAX_PARALLEL_DOWNLOADS)
    async with _sem:
        return await asyncio.to_thread(_download_sync, query, duration_hint)
