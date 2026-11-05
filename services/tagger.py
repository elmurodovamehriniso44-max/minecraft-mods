import io
import logging

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError
from PIL import Image

logger = logging.getLogger(__name__)


def prepare_cover(raw: bytes | None) -> bytes | None:
    """Muqovani kvadrat JPEG (<=600px) qiladi; YouTube thumbnail'dagi qora chiziqlarni kesadi."""
    if not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if h and abs(w / h - 4 / 3) < 0.02 and h <= 400:  # hqdefault: ustki/pastki qora chiziqlar
            bar = int(h * 0.125)
            img = img.crop((0, bar, w, h - bar))
            w, h = img.size
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        if side > 600:
            img = img.resize((600, 600))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=88)
        return out.getvalue()
    except Exception:
        logger.exception("Muqovani tayyorlashda xatolik")
        return None


def make_thumb(cover: bytes | None) -> bytes | None:
    """Telegram audio thumbnail: JPEG, <=320px, <200KB."""
    if not cover:
        return None
    try:
        img = Image.open(io.BytesIO(cover)).convert("RGB")
        img.thumbnail((320, 320))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
        return out.getvalue()
    except Exception:
        return None


def tag_mp3(path: str, title: str, artist: str, cover: bytes | None, album: str | None = None) -> None:
    """MP3 ga nom, ijrochi, albom va muqova (APIC) yozadi. Xatolik yuborishga to'sqinlik qilmaydi."""
    try:
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        for frame in ("TIT2", "TPE1", "TALB", "APIC"):
            tags.delall(frame)
        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=artist))
        tags.add(TALB(encoding=3, text=album or title))
        if cover:
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
        tags.save(path, v2_version=3)
    except Exception:
        logger.exception("ID3 teg yozishda xatolik")
