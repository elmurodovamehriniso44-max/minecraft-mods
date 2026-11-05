"""Deezer ochiq qidiruv API'si (API kaliti kerak emas).

Spotify ishlamaganda qo'shiq ro'yxati (ijrochi, nom, albom, muqova, davomiylik) uchun ishlatiladi.
Audio Deezer'dan emas, YouTube/SoundCloud'dan yuklanadi (downloader.py).
"""
import logging

import aiohttp

from services.spotifier import TrackInfo

log = logging.getLogger(__name__)

API_URL = "https://api.deezer.com/search"


async def search(query: str, limit: int = 10) -> list[TrackInfo]:
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(API_URL, params={"q": query, "limit": limit}) as resp:
                if resp.status != 200:
                    log.warning("Deezer qidiruv: HTTP %s", resp.status)
                    return []
                data = await resp.json(content_type=None)
    except Exception as e:
        log.warning("Deezer qidiruv xatosi: %s", e)
        return []

    out: list[TrackInfo] = []
    for t in data.get("data") or []:
        title = t.get("title") or ""
        artist = (t.get("artist") or {}).get("name") or ""
        if not title:
            continue
        album = t.get("album") or {}
        dur = t.get("duration") or 0
        out.append(TrackInfo(
            spotify_id=None,
            artist=artist,
            title=title,
            album=album.get("title"),
            cover_url=album.get("cover_big") or album.get("cover_medium"),
            duration_ms=dur * 1000 if dur else None,
        ))
    return out
