"""yt-dlp + ffmpeg: YouTube (cookies.txt + player_client profillari) va SoundCloud zaxira mexanizmi.

Funksiyalar:
  search_candidates(query, n)           -> YouTube/SoundCloud'dan n ta variant (qidiruv ro'yxati uchun)
  download_audio(query, hint, url=None) -> MP3 yuklaydi (url berilsa, aynan o'sha variant)
"""
import asyncio
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

from mutagen.mp3 import MP3
from yt_dlp import YoutubeDL

import config

log = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


class PreviewError(DownloadError):
    """Yuklangan fayl to'liq trek emas (odatda 30 soniyalik preview)."""


_BAD_WORDS = (
    "live", "cover", "karaoke", "remix", "reaction", "slowed", "sped up", "speed up",
    "nightcore", "8d", "instrumental", "tutorial", "mashup",
)

_sem: asyncio.Semaphore | None = None
_cookie_lock = threading.Lock()
_cookie_state: dict = {"resolved": False, "path": None}
_last_ok: dict = {"client": "unset"}   # oxirgi ishlagan player_client — keyingi safar birinchi shu sinaladi


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
        "retries": 2,
        "extractor_retries": 1,            # ishlamayotgan client'da vaqt yo'qotmaslik
        "fragment_retries": 3,
        "socket_timeout": 15,
        "geo_bypass": True,
        "noprogress": True,
        "concurrent_fragment_downloads": 4,  # HLS/DASH bo'laklarini parallel tortish
        "http_chunk_size": 10485760,         # YouTube throttling'ni kamaytiradi
    }
    if cookies:
        opts["cookiefile"] = cookies
    ff = _ffmpeg_location()
    if ff:
        opts["ffmpeg_location"] = ff
    return opts


def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


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


def _search_entries(prefix: str, query: str, cookies: str | None, n: int) -> list[dict]:
    """Qidiradi (yuklamasdan) va yaroqli natijalarni qaytaradi."""
    opts = {**_base_opts(cookies), "extract_flat": True, "skip_download": True}
    if config.PROXY_URL and prefix == "ytsearch":
        opts["proxy"] = config.PROXY_URL
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{prefix}{n}:{query}", download=False)
    source = "youtube" if prefix == "ytsearch" else "soundcloud"
    out = []
    for e in (info or {}).get("entries") or []:
        if not e:
            continue
        dur = e.get("duration")
        if dur and (dur > config.MAX_DURATION or dur < 30):  # uzun mikslar va 30s preview'lar
            continue
        url = e.get("url") or ""
        if not url.startswith("http"):
            if e.get("id") and source == "youtube":
                url = f"https://www.youtube.com/watch?v={e['id']}"
            else:
                continue
        out.append({
            "title": e.get("title") or "Nomsiz",
            "url": url,
            "duration": int(dur) if dur else None,
            "channel": e.get("channel") or e.get("uploader") or "",
            "source": source,
            "raw": e,
        })
    return out


def _search_urls(prefix: str, query: str, cookies: str | None, target: int | None, n: int = 6) -> list[str]:
    """Eng mos nomzodlar URL'lari (ball bo'yicha saralangan)."""
    q = query.lower()
    entries = _search_entries(prefix, query, cookies, n)
    entries.sort(key=lambda c: _score(c["raw"], q, target))
    return [c["url"] for c in entries]


def _check_full_length(mp3: Path, target: int | None) -> None:
    """Fayl preview (30s) bo'lib qolmaganini tekshiradi."""
    try:
        length = float(MP3(str(mp3)).info.length)
    except Exception:
        return  # o'lchab bo'lmasa, to'sqinlik qilmaymiz
    if target and target >= 45:
        bad = length < target * 0.6      # kutilgan uzunlikning 60% idan kam
    elif not target:
        bad = length <= 35               # uzunlik noma'lum: 30s preview'larni rad etamiz
    else:
        bad = False                      # juda qisqa trek
    if bad:
        raise PreviewError(f"Fayl faqat {length:.0f}s (kutilgan ~{target or '?'}s) — preview, to'liq emas")
    log.info("Uzunlik: %.0fs (kutilgan %ss)", length, target)


def _cleanup(stem: str) -> None:
    for p in config.DOWNLOAD_DIR.glob(f"{stem}*"):
        try:
            p.unlink()
        except OSError:
            pass


def _fetch(url: str, client: str | None, cookies: str | None, target: int | None = None) -> Path:
    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:12]
    opts = {
        **_base_opts(cookies),
        "format": "bestaudio[abr<=160]/bestaudio/best",  # kichik manba = tez yuklash va tez konvertatsiya
        "outtmpl": str(config.DOWNLOAD_DIR / f"{stem}.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": config.AUDIO_QUALITY}
        ],
    }
    if client:
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    if config.PROXY_URL and _is_youtube(url):
        opts["proxy"] = config.PROXY_URL
    t0 = time.monotonic()
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        log.info("⏱ yt-dlp+ffmpeg: %.1fs (client=%s)", time.monotonic() - t0, client or "default")
        mp3 = config.DOWNLOAD_DIR / f"{stem}.mp3"
        if not mp3.exists():
            raise DownloadError("MP3 fayl hosil bo'lmadi (ffmpeg o'rnatilganmi?)")
        if mp3.stat().st_size > config.MAX_FILE_MB * 1024 * 1024:
            raise DownloadError(f"Fayl {config.MAX_FILE_MB} MB dan katta")
        _check_full_length(mp3, target)
        return mp3
    except Exception:
        _cleanup(stem)
        raise


def _try_url(url: str, cookies: str | None, errors: list[str], target: int | None = None) -> Path | None:
    """Bitta URL'ni yuklashga urinadi. YouTube bo'lsa, player_client profillari ketma-ket sinaladi."""
    if _is_youtube(url):
        clients: list[str | None] = [*config.PLAYER_CLIENTS, None]  # None = yt-dlp standarti
        last = _last_ok["client"]
        if last != "unset" and last in clients:
            clients.remove(last)
            clients.insert(0, last)
        for client in clients:
            try:
                path = _fetch(url, client, cookies, target)
                _last_ok["client"] = client
                return path
            except PreviewError as e:
                errors.append(f"YT preview: {e}")
                log.warning("Preview/qisqa fayl (%s): %s", url, e)
                break  # boshqa client'lar ham xuddi shuni beradi
            except Exception as e:
                errors.append(f"YT[{client or 'default'}]: {str(e)[:150]}")
                log.warning("YouTube yuklash xatosi (%s, %s): %s", client, url, e)
    else:
        try:
            return _fetch(url, None, None, target)  # SoundCloud: YouTube cookies kerak emas
        except Exception as e:
            errors.append(f"SC: {str(e)[:150]}")
            log.warning("SoundCloud yuklash xatosi (%s): %s", url, e)
    return None


# --- Sinxron asosiy funksiyalar ---------------------------------------------
def _download_sync(query: str, duration_hint: int | None, url: str | None) -> Path:
    cookies = _prepare_cookies()
    errors: list[str] = []

    # 0) Foydalanuvchi aniq variant tanlagan bo'lsa, avval o'sha URL
    if url:
        path = _try_url(url, cookies, errors, duration_hint)
        if path:
            return path

    # 1) YouTube qidiruvi
    try:
        yt_urls = _search_urls("ytsearch", query, cookies, duration_hint)
    except Exception as e:
        errors.append(f"YT qidiruv: {e}")
        yt_urls = []
    for u in [x for x in yt_urls if x != url][:2]:
        path = _try_url(u, cookies, errors, duration_hint)
        if path:
            return path

    # 2) SoundCloud zaxira
    try:
        sc_urls = _search_urls("scsearch", query, None, duration_hint)
    except Exception as e:
        errors.append(f"SC qidiruv: {e}")
        sc_urls = []
    for u in [x for x in sc_urls if x != url][:3]:
        path = _try_url(u, None, errors, duration_hint)
        if path:
            return path

    joined = " | ".join(errors[-4:]) or "Hech narsa topilmadi"
    if "not a bot" in joined or "Sign in to confirm" in joined:
        log.error("YouTube bu server IP'sini bloklayapti. Yechim: PROXY_URL (rezident proksi) "
                  "va/yoki yangi cookies.txt. Qarang: README / .env.example")
    raise DownloadError(joined)


def _search_candidates_sync(query: str, n: int) -> list[dict]:
    cookies = _prepare_cookies()
    results: list[dict] = []
    try:
        results = _search_entries("ytsearch", query, cookies, n)
    except Exception as e:
        log.warning("YouTube qidiruv xatosi: %s", e)
    if len(results) < n:  # YouTube yetmasa yoki bloklangan bo'lsa -> SoundCloud
        try:
            results += _search_entries("scsearch", query, None, n - len(results) + 2)
        except Exception as e:
            log.warning("SoundCloud qidiruv xatosi: %s", e)
    for r in results:
        r.pop("raw", None)
    return results[:n]


# --- Async interfeys --------------------------------------------------------
async def download_audio(query: str, duration_hint: int | None = None, url: str | None = None) -> Path:
    """MP3 yuklaydi. url berilsa — aynan o'sha variant, bo'lmasa query bo'yicha eng mosi.
    Parallel yuklashlar soni cheklangan."""
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(config.MAX_PARALLEL_DOWNLOADS)
    async with _sem:
        return await asyncio.to_thread(_download_sync, query, duration_hint, url)


async def search_candidates(query: str, n: int = 24) -> list[dict]:
    """YouTube/SoundCloud variantlari: [{title, url, duration, channel, source}, ...]"""
    return await asyncio.to_thread(_search_candidates_sync, query, n)
