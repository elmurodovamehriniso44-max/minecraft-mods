import asyncio
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp
from aiogram import Bot
from aiogram.types import BufferedInputFile, FSInputFile

import config
from services import downloader, tagger
from services.db import db
from services.downloader import DownloadError

log = logging.getLogger(__name__)

SEM = asyncio.Semaphore(config.MAX_PARALLEL)


def norm_key(artist: str, title: str) -> str:
    s = f"{artist} {title}".lower()
    s = re.sub(r"[^\w\s]", "", s)
    return "q:" + " ".join(s.split())[:150]


def fmt_duration(sec: Optional[int]) -> str:
    if not sec:
        return "--:--"
    return f"{sec // 60}:{sec % 60:02d}"


@dataclass
class Prepared:
    path: Path
    workdir: Path
    title: str
    artist: str
    duration: Optional[int]
    thumb: Optional[bytes]

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


async def _fetch_bytes(url: Optional[str]) -> Optional[bytes]:
    if not url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        log.warning("Muqova yuklanmadi: %s", e)
    return None


async def targets_for_query(query: str) -> list[str]:
    """Qo'shiqning original audiosini topish uchun manbalar ro'yxati (YouTube -> SoundCloud)."""
    targets: list[str] = []
    try:
        for r in await downloader.search(query, 5):
            d = r.get("duration")
            if d and 60 <= d <= config.MAX_TRACK_SECONDS:
                targets.append(f"https://www.youtube.com/watch?v={r['id']}")
                break
    except Exception as e:
        log.warning("YouTube qidiruv xatosi: %s", e)
    targets.append(f"scsearch1:{query}")
    return targets


async def prepare(
    targets: list[str],
    title: Optional[str] = None,
    artist: Optional[str] = None,
    cover_url: Optional[str] = None,
) -> Prepared:
    """Yuklaydi, ID3 teglar va muqovani yozadi. Chaqiruvchi cleanup() qilishi shart."""
    async with SEM:
        workdir = Path(tempfile.mkdtemp(prefix="trk_", dir=config.TMP_DIR))
        try:
            path = info = None
            last_err: Optional[Exception] = None
            for t in targets:
                try:
                    path, info = await downloader.download_audio(
                        t, workdir, bitrate="192", max_duration=config.MAX_TRACK_SECONDS
                    )
                    break
                except Exception as e:
                    last_err = e
                    log.warning("Manba ishlamadi (%s): %s", t, e)
            if path is None or info is None:
                raise DownloadError(str(last_err) if last_err else "Manba topilmadi")

            title = title or info.get("track") or info.get("title") or "Unknown"
            artist = artist or info.get("artist") or info.get("uploader") or info.get("channel") or ""

            raw = await _fetch_bytes(cover_url or info.get("thumbnail"))
            cover = tagger.to_jpeg(raw, 600) if raw else None
            thumb = tagger.to_jpeg(cover, 320, 190 * 1024) if cover else None
            await tagger.write_tags(path, title, artist, cover)

            if path.stat().st_size > config.MAX_FILE_BYTES:
                raise DownloadError("Fayl Telegram limitidan (50 MB) katta")

            dur = info.get("duration")
            return Prepared(path, workdir, title, artist, int(dur) if dur else None, thumb)
        except BaseException:
            shutil.rmtree(workdir, ignore_errors=True)
            raise


async def send_prepared(bot: Bot, chat_id: int, p: Prepared, with_caption: bool = True) -> str:
    """Audioni yuboradi va Telegram file_id ni qaytaradi."""
    safe = re.sub(r'[\\/:*?"<>|]', "", f"{p.artist} - {p.title}".strip(" -"))[:100] or "track"
    caption = None
    if with_caption:
        me = await bot.me()
        caption = f"🎧 @{me.username}"
    msg = await bot.send_audio(
        chat_id=chat_id,
        audio=FSInputFile(p.path, filename=f"{safe}.mp3"),
        title=p.title,
        performer=p.artist,
        duration=p.duration,
        thumbnail=BufferedInputFile(p.thumb, "cover.jpg") if p.thumb else None,
        caption=caption,
    )
    return msg.audio.file_id


async def ensure_youtube_cached(bot: Bot, vid: str, upload_chat_id: int) -> tuple[str, bool]:
    """(file_id, shu chatga yuborildimi) qaytaradi."""
    key = f"yt:{vid}"
    tr = await db.get_track(key)
    if tr:
        return tr["file_id"], False
    prep = await prepare([f"https://www.youtube.com/watch?v={vid}"])
    try:
        fid = await send_prepared(bot, upload_chat_id, prep)
    finally:
        prep.cleanup()
    await db.save_track(key, fid, prep.title, prep.artist)
    return fid, True
