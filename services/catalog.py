"""Qidiruv: Deezer katalogi (toza nom, ijrochi, muqova) + YouTube (mahalliy va boshqa treklar uchun)."""
import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

from services import downloader, utils

log = logging.getLogger(__name__)
DEEZER = "https://api.deezer.com"


@dataclass
class Item:
    kind: str  # "d" = Deezer, "y" = YouTube
    id: str
    title: str
    artist: str
    duration: Optional[int] = None
    cover: Optional[str] = None
    preview: Optional[str] = None

    @property
    def key(self) -> str:
        return utils.norm_key(self.artist, self.title) if self.kind == "d" else f"yt:{self.id}"

    @property
    def cb(self) -> str:
        return f"{self.kind}:{self.id}"

    @property
    def label(self) -> str:
        base = f"🎵 {self.artist} — {self.title}" if self.kind == "d" else f"▶️ {self.title}"
        return f"{base[:50]} · {utils.fmt_duration(self.duration)}"


ITEMS: dict[tuple[str, str], Item] = {}
SESSIONS: dict[str, tuple[float, list[Item]]] = {}


def remember(items: list[Item]) -> None:
    for it in items:
        ITEMS[(it.kind, it.id)] = it
    if len(ITEMS) > 3000:
        for k in list(ITEMS)[:1000]:
            ITEMS.pop(k, None)


def new_session(items: list[Item]) -> str:
    now = time.time()
    for k in [k for k, (t, _) in SESSIONS.items() if now - t > 3600]:
        SESSIONS.pop(k, None)
    sid = secrets.token_hex(3)
    SESSIONS[sid] = (now, items)
    return sid


def get_session(sid: str) -> Optional[list[Item]]:
    v = SESSIONS.get(sid)
    return v[1] if v else None


async def _deezer(path: str, params: Optional[dict] = None) -> dict:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(DEEZER + path, params=params) as r:
            data = await r.json(content_type=None)
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"Deezer: {data['error']}")
    return data


def _from_deezer(t: dict) -> Item:
    album = t.get("album") or {}
    return Item(
        kind="d",
        id=str(t["id"]),
        title=t.get("title") or "Nomsiz",
        artist=(t.get("artist") or {}).get("name") or "",
        duration=t.get("duration"),
        cover=album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium"),
        preview=t.get("preview") or None,
    )


async def search(query: str, limit: int = 24) -> list[Item]:
    d_res, y_res = await asyncio.gather(
        _deezer("/search", {"q": query, "limit": 12}),
        asyncio.wait_for(downloader.search(query, 12), timeout=9),
        return_exceptions=True,
    )
    d: list[Item] = []
    y: list[Item] = []
    if isinstance(d_res, BaseException):
        log.warning("Deezer qidiruv xatosi: %s", d_res)
    else:
        d = [_from_deezer(t) for t in d_res.get("data", []) if t.get("id")]
    if isinstance(y_res, BaseException):
        log.warning("YouTube qidiruv xatosi: %s", y_res)
    else:
        y = [Item("y", r["id"], r["title"], r["uploader"], r["duration"]) for r in y_res]
    if isinstance(d_res, BaseException) and isinstance(y_res, BaseException):
        raise RuntimeError("Qidiruv manbalari ishlamadi")

    merged: list[Item] = []
    seen: set[tuple[str, str]] = set()
    for it in d[:5] + y[:3] + d[5:] + y[3:]:
        if (it.kind, it.id) in seen:
            continue
        seen.add((it.kind, it.id))
        merged.append(it)
    merged = merged[:limit]
    remember(merged)
    return merged


async def chart(limit: int = 20) -> list[Item]:
    data = await _deezer("/chart/0/tracks", {"limit": limit})
    items = [_from_deezer(t) for t in data.get("data", []) if t.get("id")]
    remember(items)
    return items


async def resolve(kind: str, ident: str) -> Item:
    it = ITEMS.get((kind, ident))
    if it:
        return it
    if kind == "d":
        it = _from_deezer(await _deezer(f"/track/{ident}"))
    else:
        it = Item("y", ident, "", "")
    remember([it])
    return it


async def enrich(item: Item) -> None:
    """Shazam topgan qo'shiq uchun Deezer'dan davomiylik, muqova va 30s namuna olish."""
    try:
        data = await _deezer("/search", {"q": f"{item.artist} {item.title}", "limit": 1})
        arr = data.get("data") or []
        if not arr:
            return
        d = _from_deezer(arr[0])
        if utils.tokens(item.title) & utils.tokens(d.title):
            item.duration = item.duration or d.duration
            item.cover = item.cover or d.cover
            item.preview = d.preview
    except Exception as e:
        log.info("Deezer enrich xatosi: %s", e)
