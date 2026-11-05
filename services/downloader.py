"""yt-dlp orqali audio olish.

Render kabi datacenter IP'larida YouTube ko'pincha bloklaydi, shuning uchun:
  * cookies.txt qo'llab-quvvatlanadi (har ishda yozish mumkin bo'lgan nusxasi olinadi);
  * player_client profillari (web/android/ios) ketma-ket sinab ko'riladi;
  * YouTube ishlamasa SoundCloud zaxira manba sifatida ishlatiladi.
"""
import asyncio
import glob
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import yt_dlp
from yt_dlp.utils import DownloadError as YtdlpError

import config
from services import utils

logger = logging.getLogger(__name__)


class DownloaderError(Exception):
    pass


class TooLong(DownloaderError):
    pass


class TooBig(DownloaderError):
    pass


_BLOCK_MARKERS = (
    "sign in to confirm", "not a bot", "http error 429", "http error 403",
    "po token", "login required", "cookies", "confirm your age",
)


def looks_blocked(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _BLOCK_MARKERS)


@dataclass
class SearchResult:
    video_id: str
    title: str
    artist: str
    duration: int | None
    raw_title: str = ""
    channel: str = ""


@dataclass
class Fetched:
    path: str
    source: str            # "youtube" | "soundcloud"
    source_id: str | None
    title: str
    artist: str
    duration: int


# ---------------- yordamchilar ----------------
_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*(official|lyric|audio|video|clip|hd|hq|4k)[^\)\]]*[\)\]]", re.I
)
_META: dict[str, tuple[str, str]] = {}  # video_id -> (artist, title)


def split_title(raw: str, uploader: str | None) -> tuple[str, str]:
    t = _NOISE.sub("", raw or "").strip()
    for sep in (" - ", " – ", " — "):
        if sep in t:
            a, s = t.split(sep, 1)
            return a.strip(), s.strip()
    artist = (uploader or "Noma'lum").replace(" - Topic", "").strip()
    return artist, t


def recall(video_id: str) -> tuple[str | None, str | None]:
    return _META.get(video_id, (None, None))


def thumb_url(video_id: str | None) -> str | None:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None


def _is_youtube(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return host.endswith(("youtube.com", "youtu.be", "youtube-nocookie.com"))


def _base_opts(tmp: str, clients: list[str] | None = None, cookies: bool = True) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 2,
        "geo_bypass": True,
    }
    ff = utils.find_ffmpeg()
    if ff:
        opts["ffmpeg_location"] = os.path.dirname(ff)
    if cookies and config.COOKIES_FILE:
        # Render Secret File faqat o'qish uchun; yt-dlp esa cookie faylga qayta yozadi -> nusxa olamiz
        dst = os.path.join(tmp, "cookies.txt")
        if not os.path.exists(dst):
            shutil.copyfile(config.COOKIES_FILE, dst)
        opts["cookiefile"] = dst
    if clients:
        opts["extractor_args"] = {"youtube": {"player_client": clients}}
    return opts


def _profiles(youtube: bool) -> list[list[str] | None]:
    return [[c] for c in config.YT_PLAYER_CLIENTS] if youtube else [None]


def _with_profiles(fn, youtube: bool):
    last: Exception | None = None
    for clients in _profiles(youtube):
        try:
            return fn(clients)
        except (TooLong, TooBig):
            raise
        except Exception as e:
            last = e
            logger.warning("player_client=%s muvaffaqiyatsiz: %s", clients, str(e)[:200])
    raise DownloaderError(str(last)) from last


async def _run(fn, *args, timeout: int):
    return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout)


# ---------------- 1) havoladan audio olish ----------------
def _source_sync(url: str, tmp: str) -> str:
    def attempt(clients):
        opts = {
            **_base_opts(tmp, clients),
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmp, "src.%(ext)s"),
            "max_filesize": 200 * 1024 * 1024,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("entries"):
                info = next((e for e in info["entries"] if e), None)
            if not info:
                raise DownloaderError("Videoni topib bo'lmadi")
            dur = int(info.get("duration") or 0)
            if dur and dur > config.LINK_MAX_DURATION:
                raise TooLong(dur)
            ydl.process_ie_result(info, download=True)
        for f in sorted(glob.glob(os.path.join(tmp, "src.*"))):
            if not f.endswith((".part", ".ytdl")):
                return f
        raise DownloaderError("Audio fayl yuklanmadi")

    return _with_profiles(attempt, _is_youtube(url))


async def download_source_audio(url: str, tmp: str) -> str:
    """Havoladagi videoning audio qismini `tmp` (workdir ichida) ga tortadi."""
    return await _run(_source_sync, url, tmp, timeout=180)


# ---------------- 2) YouTube qidiruv ----------------
_search_cache: dict[str, tuple[float, list[SearchResult]]] = {}


def _search_sync(query: str, limit: int) -> list[SearchResult]:
    def attempt(clients):
        with utils.tempdir() as tmp:
            opts = {**_base_opts(tmp, clients), "extract_flat": True, "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    data = _with_profiles(attempt, True)
    results: list[SearchResult] = []
    for e in (data or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        dur = e.get("duration")
        if dur and not (config.TRACK_MIN_DURATION <= dur <= config.TRACK_MAX_DURATION):
            continue
        channel = e.get("channel") or e.get("uploader") or ""
        artist, title = split_title(e.get("title", ""), channel)
        results.append(SearchResult(e["id"], title, artist, int(dur) if dur else None, e.get("title", ""), channel))
        if len(_META) > 5000:
            _META.clear()
        _META[e["id"]] = (artist, title)
    return results


async def search_youtube(query: str, limit: int = config.SEARCH_LIMIT) -> list[SearchResult]:
    key = f"{limit}:{query.lower().strip()}"
    hit = _search_cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        results = await _run(_search_sync, query, limit, timeout=45)
    except asyncio.TimeoutError:
        raise DownloaderError("Qidiruv vaqti tugadi")
    if len(_search_cache) > 300:
        _search_cache.clear()
    _search_cache[key] = (time.time(), results)
    return results


_BAD_TAGS = ("live", "cover", "remix", "karaoke", "reaction", "slowed", "sped up", "nightcore", "8d", "instrumental", "mashup")


def rank_candidates(results: list[SearchResult], artist: str, title: str) -> list[SearchResult]:
    """Original studiya variantini (Topic / Official Audio) yuqoriga chiqaradi."""
    q = f"{artist} {title}".lower()
    t_words = [w for w in re.findall(r"\w+", title.lower()) if len(w) > 2]
    a_words = [w for w in re.findall(r"\w+", artist.lower()) if len(w) > 2]

    def score(r: SearchResult) -> float:
        raw, ch = r.raw_title.lower(), r.channel.lower()
        s = 0.0
        if ch.endswith("topic"):
            s += 3
        if "official audio" in raw or "(audio)" in raw:
            s += 2
        elif "official" in raw:
            s += 1
        s -= sum(3 for tag in _BAD_TAGS if tag in raw and tag not in q)
        if t_words:
            s += 2 * sum(w in raw for w in t_words) / len(t_words)
        if a_words:
            s += sum(w in raw or w in ch for w in a_words) / len(a_words)
        return s

    return sorted(results, key=lambda r: -score(r))


# ---------------- 3) to'liq MP3 yuklash ----------------
def _mp3_opts(tmp: str, name: str, clients, cookies: bool = True) -> dict:
    return {
        **_base_opts(tmp, clients, cookies),
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp, f"{name}.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": config.MP3_BITRATE}
        ],
    }


def _finish(path: str, source: str, source_id, artist, title, info, dur) -> Fetched:
    if not os.path.exists(path):
        raise DownloaderError("MP3 fayl yaratilmadi")
    if os.path.getsize(path) > config.MAX_FILE_BYTES:
        raise TooBig()
    if not (artist and title):
        if info.get("artist") and info.get("track"):
            artist, title = str(info["artist"]), str(info["track"])
        else:
            artist, title = split_title(info.get("title", ""), info.get("uploader"))
    return Fetched(path, source, source_id, title, artist, dur)


def _youtube_sync(video_id: str, tmp: str, artist: str | None, title: str | None) -> Fetched:
    url = f"https://www.youtube.com/watch?v={video_id}"

    def attempt(clients):
        with yt_dlp.YoutubeDL(_mp3_opts(tmp, video_id, clients)) as ydl:
            info = ydl.extract_info(url, download=False)
            dur = int(info.get("duration") or 0)
            if dur > config.TRACK_MAX_DURATION:
                raise TooLong(dur)
            ydl.process_ie_result(info, download=True)
        return _finish(os.path.join(tmp, f"{video_id}.mp3"), "youtube", video_id, artist, title, info, dur)

    return _with_profiles(attempt, True)


def _soundcloud_sync(query: str, tmp: str, artist: str | None, title: str | None) -> Fetched:
    with yt_dlp.YoutubeDL({**_base_opts(tmp, None, cookies=False), "extract_flat": True, "skip_download": True}) as ydl:
        data = ydl.extract_info(f"scsearch5:{query}", download=False)
    pick = None
    for e in (data or {}).get("entries") or []:
        dur = e.get("duration") or 0
        if e.get("url") and (not dur or config.TRACK_MIN_DURATION <= dur <= config.TRACK_MAX_DURATION):
            pick = e
            break
    if not pick:
        raise DownloaderError("SoundCloud'da topilmadi")
    with yt_dlp.YoutubeDL(_mp3_opts(tmp, "sc", None, cookies=False)) as ydl:
        info = ydl.extract_info(pick["url"], download=True)
    return _finish(os.path.join(tmp, "sc.mp3"), "soundcloud", None, artist, title, info, int(info.get("duration") or 0))


async def fetch_track(tmp: str, artist: str | None, title: str | None, video_id: str | None = None) -> Fetched:
    """To'liq MP3: YouTube (video_id yoki qidiruv) -> SoundCloud zaxira."""
    errors: list[Exception] = []
    candidates: list[str] = []
    if video_id:
        candidates.append(video_id)
        if not (artist and title):
            artist, title = _META.get(video_id, (artist, title))
    elif artist and title:
        try:
            found = await search_youtube(f"{artist} - {title}", 10)
            candidates += [r.video_id for r in rank_candidates(found, artist, title)[:3]]
        except Exception as e:
            errors.append(e)

    for vid in candidates:
        try:
            return await _run(_youtube_sync, vid, tmp, artist, title, timeout=240)
        except TooLong as e:
            if video_id:
                raise
            errors.append(e)
        except Exception as e:
            errors.append(e)
            logger.warning("YouTube %s yuklanmadi: %s", vid, str(e)[:200])
            if looks_blocked(e):
                break  # boshqa video ham bloklanadi, SoundCloud'ga o'tamiz

    if artist and title:
        try:
            return await _run(_soundcloud_sync, f"{artist} {title}", tmp, artist, title, timeout=240)
        except Exception as e:
            errors.append(e)
            logger.warning("SoundCloud zaxira ham ishlamadi: %s", str(e)[:200])

    raise DownloaderError(" | ".join(str(e)[:150] for e in errors) or "Qo'shiq topilmadi")
