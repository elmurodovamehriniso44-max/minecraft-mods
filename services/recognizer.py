import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass

from shazamio import Shazam

from services import utils

logger = logging.getLogger(__name__)

# (boshlanish, davomiylik) sekundlarda: avval boshidan, topilmasa o'rtasidan/oxiridan
WINDOWS = [(0, 20), (20, 20), (45, 20)]
MIN_CLIP_BYTES = 160_000  # ~5 soniya 16kHz mono WAV


@dataclass
class Recognized:
    key: str
    title: str
    artist: str
    cover_url: str | None


async def _make_clip(src: str, start: int, dur: int, out: str) -> bool:
    try:
        await utils.run_ffmpeg(
            ["-ss", str(start), "-t", str(dur), "-i", src, "-vn",
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out],
            timeout=60,
        )
    except Exception as e:
        logger.warning("Klip kesishda xatolik (%ss): %s", start, e)
        return False
    return os.path.exists(out) and os.path.getsize(out) >= MIN_CLIP_BYTES


async def recognize(src: str, workdir: str) -> Recognized | None:
    """Audio fayldan qisqa bo'laklar kesib, shazamio orqali tanib oladi. Topilmasa None."""
    shazam = Shazam()
    for i, (start, dur) in enumerate(WINDOWS):
        clip = os.path.join(workdir, f"clip{i}.wav")
        if not await _make_clip(src, start, dur, clip):
            break  # audio tugagan yoki ovoz yo'q
        try:
            out = await asyncio.wait_for(shazam.recognize(clip), timeout=45)
        except Exception as e:
            logger.warning("Shazam so'rovi muvaffaqiyatsiz (%ss): %s", start, e)
            continue
        track = (out or {}).get("track")
        if not track:
            continue
        title = (track.get("title") or "").strip()
        artist = (track.get("subtitle") or "").strip()
        if not title:
            continue
        images = track.get("images") or {}
        key = str(track.get("key") or hashlib.sha1(f"{artist}{title}".lower().encode()).hexdigest()[:12])
        return Recognized(key, title, artist or "Noma'lum", images.get("coverarthq") or images.get("coverart"))
    return None
