"""mutagen: mp3 faylga ID3 teglari va muqova (cover art) yozish."""
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TPE2, ID3NoHeaderError
from mutagen.mp3 import MP3


def tag_mp3(path, title: str, artist: str | None, album: str | None, cover: bytes | None) -> None:
    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()

    for frame in ("TIT2", "TPE1", "TPE2", "TALB", "APIC"):
        tags.delall(frame)

    tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
        tags.add(TPE2(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if cover:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))

    tags.save(str(path), v2_version=3)


def get_duration(path) -> int | None:
    try:
        return int(MP3(str(path)).info.length)
    except Exception:
        return None
