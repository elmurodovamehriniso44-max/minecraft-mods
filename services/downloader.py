import asyncio
import logging
import time
from pathlib import Path

import yt_dlp

import config

log = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


def _base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
    }
    if config.COOKIES_FILE:
        opts["cookiefile"] = config.COOKIES_FILE
    if config.PROXY:
        opts["proxy"] = config.PROXY
    return opts


def _download_sync(target: str, workdir: Path, bitrate: str, max_duration: int) -> tuple[Path, dict]:
    opts = _base_opts() | {
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "audio.%(ext)s"),
        "match_filter": yt_dlp.utils.match_filter_func(f"duration <=? {max_duration} & !is_live"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate}
        ],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(str(e)) from e

    if not info:
        raise DownloadError("Video filtrdan o'tmadi (juda uzun yoki jonli efir)")
    if info.get("entries"):
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise DownloadError("Hech narsa topilmadi")
        info = entries[0]

    mp3 = workdir / "audio.mp3"
    if not mp3.exists():
        raise DownloadError("MP3 fayl yaratilmadi (ffmpeg o'rnatilganmi?)")
    return mp3, info


async def download_audio(
    target: str, workdir: Path, bitrate: str = "192", max_duration: int = config.MAX_TRACK_SECONDS
) -> tuple[Path, dict]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_sync, target, workdir, bitrate, max_duration), timeout=180
        )
    except asyncio.TimeoutError as e:
        raise DownloadError("Yuklash vaqti tugadi") from e


# ---------- YouTube qidiruv ----------
_cache: dict[str, tuple[float, list[dict]]] = {}


def _search_sync(query: str, limit: int) -> list[dict]:
    opts = _base_opts() | {"extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    out = []
    for e in (info or {}).get("entries") or []:
        if not e or len(e.get("id", "")) != 11:
            continue
        out.append(
            {
                "id": e["id"],
                "title": e.get("title") or "Nomsiz",
                "duration": int(e["duration"]) if e.get("duration") else None,
                "uploader": e.get("channel") or e.get("uploader") or "",
            }
        )
    return out


async def search(query: str, limit: int = 10) -> list[dict]:
    key = f"{limit}:{query.lower()}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    res = await asyncio.wait_for(asyncio.to_thread(_search_sync, query, limit), timeout=25)
    _cache[key] = (time.time(), res)
    if len(_cache) > 500:
        for k, _ in sorted(_cache.items(), key=lambda kv: kv[1][0])[:100]:
            _cache.pop(k, None)
    return res
