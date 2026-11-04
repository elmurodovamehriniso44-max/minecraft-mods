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
from services import downloader, tagger, utils
from services.catalog import Item
from services.db import db
from services.downloader import DownloadError

log = logging.getLogger(__name__)
SEM = asyncio.Semaphore(config.MAX_PARALLEL)

BAD_WORDS = ("lyrics", "lyric", "live", "remix", "cover", "karaoke", "slowed", "sped", "reverb",
             "8d", "nightcore", "instrumental", "reaction", "tutorial")


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
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        log.warning("Yuklab bo'lmadi (%s): %s", url, e)
    return None


def _score(c: dict, item: Item) -> float:
    t = c["title"].lower()
    s = 0.0
    if c["duration"] is None:
        s -= 30
    else:
        if c["duration"] > config.MAX_TRACK_SECONDS:
            return -10_000
        if item.duration:
            s -= abs(item.duration - c["duration"])
    for w in BAD_WORDS:
        if w in t and w not in item.title.lower():
            s -= 25
    if "official" in t or "audio" in t or "topic" in c["uploader"].lower():
        s += 10
    first_artist = item.artist.lower().split(",")[0].strip()
    if first_artist and (first_artist in t or first_artist in c["uploader"].lower()):
        s += 10
    return s


async def targets_for_item(item: Item) -> list[str]:
    if item.kind == "y":
        targets = [f"https://www.youtube.com/watch?v={item.id}"]
        if item.title:
            targets.append(f"scsearch1:{utils.clean_title(item.title)}")
        return targets

    query = f"{item.artist} - {item.title}"
    targets: list[str] = []
    try:
        cands = await downloader.search(query, 8)
        ranked = sorted(cands, key=lambda c: _score(c, item), reverse=True)
        for c in ranked[:2]:
            if _score(c, item) > -500:
                targets.append(f"https://www.youtube.com/watch?v={c['id']}")
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
            errors: list[str] = []
            for t in targets:
                try:
                    path, info = await downloader.download_audio(
                        t, workdir, bitrate="192", max_duration=config.MAX_TRACK_SECONDS
                    )
                    break
                except Exception as e:
                    errors.append(utils.short_err(e, 160))
                    log.warning("Manba ishlamadi (%s): %s", t, e)
            if path is None or info is None:
                raise DownloadError(" | ".join(errors) or "Manba topilmadi")

            if not (title and artist):
                if info.get("track") and info.get("artist"):
                    t2, a2 = info["track"], info["artist"]
                else:
                    a2, t2 = utils.split_artist_title(
                        info.get("title") or "", info.get("uploader") or info.get("channel") or ""
                    )
                title = title or t2 or "Unknown"
                artist = artist or a2 or ""

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


async def prepare_preview(item: Item) -> Prepared:
    """Oxirgi chora: Deezer'ning 30 soniyalik rasmiy namunasi."""
    workdir = Path(tempfile.mkdtemp(prefix="prv_", dir=config.TMP_DIR))
    try:
        data = await _fetch_bytes(item.preview)
        if not data:
            raise DownloadError("Namuna yuklanmadi")
        path = workdir / "audio.mp3"
        path.write_bytes(data)
        raw = await _fetch_bytes(item.cover)
        cover = tagger.to_jpeg(raw, 600) if raw else None
        thumb = tagger.to_jpeg(cover, 320, 190 * 1024) if cover else None
        await tagger.write_tags(path, item.title, item.artist, cover)
        return Prepared(path, workdir, item.title, item.artist, 30, thumb)
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


async def send_prepared(bot: Bot, chat_id: int, p: Prepared, note: str = "") -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "", f"{p.artist} - {p.title}".strip(" -"))[:100] or "track"
    me = await bot.me()
    caption = f"🎧 @{me.username}" + (f"\n{note}" if note else "")
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


async def get_file_id(bot: Bot, item: Item, upload_chat_id: int) -> tuple[str, bool, bool]:
    """(file_id, upload_chatga_yuborildimi, faqat_namunami)"""
    cached = await db.get_track(item.key)
    if cached:
        return cached["file_id"], False, False

    targets = await targets_for_item(item)
    prep: Optional[Prepared] = None
    preview = False
    try:
        try:
            prep = await prepare(
                targets,
                item.title if item.kind == "d" else None,
                item.artist if item.kind == "d" else None,
                item.cover,
            )
        except Exception as e:
            if item.preview:
                log.warning("To'liq versiya topilmadi, namuna yuboriladi: %s", e)
                prep = await prepare_preview(item)
                preview = True
            else:
                raise
        note = "⚠️ To'liq versiya topilmadi — 30 soniyalik namuna." if preview else ""
        fid = await send_prepared(bot, upload_chat_id, prep, note)
    finally:
        if prep:
            prep.cleanup()
    if not preview:
        await db.save_track(item.key, fid, prep.title, prep.artist)
    return fid, True, preview
