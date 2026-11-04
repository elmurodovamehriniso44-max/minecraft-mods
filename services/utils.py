import re
from typing import Optional


def norm_key(artist: str, title: str) -> str:
    s = f"{artist} {title}".lower()
    s = re.sub(r"[^\w\s]", "", s)
    return "q:" + " ".join(s.split())[:150]


def fmt_duration(sec: Optional[int]) -> str:
    if not sec:
        return "--:--"
    return f"{sec // 60}:{sec % 60:02d}"


_TAG_RE = re.compile(
    r"\s*[\(\[][^)\]]*(official|lyrics?|video|audio|hd|4k|visuali[sz]er|clip|mv|music)[^)\]]*[\)\]]",
    re.I,
)


def clean_title(t: str) -> str:
    t = _TAG_RE.sub("", t or "")
    return " ".join(t.split()).strip(" -–|")


def split_artist_title(raw: str, uploader: str) -> tuple[str, str]:
    t = clean_title(raw)
    for sep in (" - ", " – ", " — "):
        if sep in t:
            a, b = t.split(sep, 1)
            if a.strip() and b.strip():
                return a.strip(), b.strip()
    up = re.sub(r"\s*-\s*Topic$", "", uploader or "")
    return up, t


def tokens(s: str) -> set[str]:
    return {w for w in re.sub(r"[^\w\s]", " ", (s or "").lower()).split() if len(w) > 1}


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def short_err(e: BaseException, n: int = 260) -> str:
    s = _ANSI.sub("", str(e)).strip() or e.__class__.__name__
    return s[-n:]
