import asyncio
import io
from pathlib import Path
from typing import Optional

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TIT2, TPE1


def to_jpeg(data: bytes, max_side: int, max_bytes: Optional[int] = None) -> Optional[bytes]:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((max_side, max_side))
        quality = 90
        while True:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            if not max_bytes or buf.tell() <= max_bytes or quality <= 40:
                return buf.getvalue()
            quality -= 10
    except Exception:
        return None


def _write_sync(path: Path, title: str, artist: str, cover_jpeg: Optional[bytes]) -> None:
    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    if cover_jpeg:
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_jpeg))
    tags.save(str(path), v2_version=3)


async def write_tags(path: Path, title: str, artist: str, cover_jpeg: Optional[bytes]) -> None:
    await asyncio.to_thread(_write_sync, path, title, artist, cover_jpeg)
