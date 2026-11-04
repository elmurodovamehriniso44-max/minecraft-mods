import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shazamio import Shazam

log = logging.getLogger(__name__)


@dataclass
class Recognized:
    title: str
    artist: str
    cover_url: Optional[str]


async def _cut(src: Path, dst: Path, start: int, dur: int = 20) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(start), "-t", str(dur), "-i", str(src),
        "-vn", "-ac", "1", "-ar", "44100", str(dst),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        return False
    return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 4000


async def recognize(audio: Path, workdir: Path) -> Optional[Recognized]:
    """Audioning bir necha bo'lagini Shazam orqali tekshiradi."""
    shazam = Shazam()
    fn = getattr(shazam, "recognize", None) or getattr(shazam, "recognize_song")
    for start in (0, 12, 30):
        seg = workdir / f"seg_{start}.wav"
        if not await _cut(audio, seg, start):
            continue
        try:
            out = await asyncio.wait_for(fn(str(seg)), timeout=45)
        except Exception as e:
            log.warning("Shazam xatosi (start=%s): %s", start, e)
            continue
        track = (out or {}).get("track")
        if track and track.get("title"):
            images = track.get("images") or {}
            return Recognized(
                title=track["title"],
                artist=track.get("subtitle") or "",
                cover_url=images.get("coverarthq") or images.get("coverart"),
            )
    return None
