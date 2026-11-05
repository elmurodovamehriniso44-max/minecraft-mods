"""Spotify havolalari va qidiruv (spotipy, Client Credentials)."""
import asyncio
import logging
import re
from dataclasses import dataclass, field

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

import config
from services.utils import normalize_key

log = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-zA-Z-]+/)?(track|album)/([A-Za-z0-9]{22})"
)


class SpotifyError(Exception):
    pass


@dataclass
class TrackInfo:
    spotify_id: str | None
    artist: str
    title: str
    album: str | None = None
    cover_url: str | None = None
    duration_ms: int | None = None

    @property
    def display(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist else self.title

    @property
    def cache_key(self) -> str:
        return normalize_key(f"{self.artist} {self.title}")

    @property
    def duration_s(self) -> int | None:
        return round(self.duration_ms / 1000) if self.duration_ms else None


@dataclass
class AlbumInfo:
    spotify_id: str
    name: str
    artist: str
    cover_url: str | None
    tracks: list[TrackInfo] = field(default_factory=list)


def parse_url(text: str) -> tuple[str, str] | None:
    m = _URL_RE.search(text or "")
    return (m.group(1), m.group(2)) if m else None


_client: spotipy.Spotify | None = None


def _sp() -> spotipy.Spotify:
    global _client
    if _client is None:
        if not (config.SPOTIFY_CLIENT_ID and config.SPOTIFY_CLIENT_SECRET):
            raise SpotifyError("Spotify kalitlari o'rnatilmagan")
        _client = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=config.SPOTIFY_CLIENT_ID, client_secret=config.SPOTIFY_CLIENT_SECRET
            ),
            requests_timeout=10, retries=2,
        )
    return _client


def _pick_cover(images: list[dict] | None) -> str | None:
    if not images:
        return None
    imgs = sorted(images, key=lambda i: i.get("width") or 0)
    for img in imgs:  # eng kichik, lekin >= 300px
        if (img.get("width") or 0) >= 300:
            return img["url"]
    return imgs[-1]["url"]


def _to_track(t: dict, album: dict | None = None) -> TrackInfo:
    album = t.get("album") or album or {}
    return TrackInfo(
        spotify_id=t.get("id"),
        artist=", ".join(a["name"] for a in t.get("artists", [])),
        title=t.get("name", ""),
        album=album.get("name"),
        cover_url=_pick_cover(album.get("images")),
        duration_ms=t.get("duration_ms"),
    )


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except SpotifyError:
        raise
    except Exception as e:
        log.warning("Spotify xatosi: %s", e)
        raise SpotifyError(str(e)) from e


async def get_track(spotify_id: str) -> TrackInfo:
    data = await asyncio.to_thread(_wrap, lambda: _sp().track(spotify_id))
    return _to_track(data)


async def get_album(spotify_id: str) -> AlbumInfo:
    data = await asyncio.to_thread(_wrap, lambda: _sp().album(spotify_id))
    tracks = [_to_track(t, album=data) for t in (data.get("tracks") or {}).get("items", []) if t.get("id")]
    return AlbumInfo(
        spotify_id=spotify_id,
        name=data.get("name", ""),
        artist=", ".join(a["name"] for a in data.get("artists", [])),
        cover_url=_pick_cover(data.get("images")),
        tracks=tracks,
    )


async def search(query: str, limit: int = 8) -> list[TrackInfo]:
    data = await asyncio.to_thread(
        _wrap, lambda: _sp().search(q=query, type="track", limit=min(limit, 10))
    )
    return [_to_track(t) for t in data.get("tracks", {}).get("items", []) if t and t.get("id")]
