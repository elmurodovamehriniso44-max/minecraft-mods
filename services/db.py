"""SQLite: foydalanuvchilar, statistika va file_id kesh."""
import aiosqlite

import config
from services.utils import normalize_key

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    joined_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    last_active TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tracks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key   TEXT UNIQUE NOT NULL,
    spotify_id  TEXT,
    artist      TEXT,
    title       TEXT,
    album       TEXT,
    cover_url   TEXT,
    duration    INTEGER,
    file_id     TEXT NOT NULL,
    search_text TEXT,
    downloads   INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tracks_spotify ON tracks(spotify_id);
CREATE TABLE IF NOT EXISTS downloads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    track_id   INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def _c() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Baza ishga tushirilmagan: db.init() chaqiring")
    return _db


async def init() -> None:
    global _db
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(config.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(SCHEMA)
    await _db.commit()


async def close() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _one(sql: str, params: tuple = ()) -> dict | None:
    cur = await _c().execute(sql, params)
    row = await cur.fetchone()
    return dict(row) if row else None


async def _all(sql: str, params: tuple = ()) -> list[dict]:
    cur = await _c().execute(sql, params)
    return [dict(r) for r in await cur.fetchall()]


async def _scalar(sql: str, params: tuple = ()) -> int:
    cur = await _c().execute(sql, params)
    row = await cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# --- Foydalanuvchilar -------------------------------------------------------
async def upsert_user(user_id: int, username: str | None, full_name: str | None) -> None:
    await _c().execute(
        """INSERT INTO users(user_id, username, full_name) VALUES(?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
               full_name=excluded.full_name, last_active=CURRENT_TIMESTAMP""",
        (user_id, username, full_name),
    )
    await _c().commit()


async def all_user_ids() -> list[int]:
    return [r["user_id"] for r in await _all("SELECT user_id FROM users")]


# --- Treklar (file_id kesh) -------------------------------------------------
async def find_cached(spotify_id: str | None, cache_key: str) -> dict | None:
    if spotify_id:
        row = await _one("SELECT * FROM tracks WHERE spotify_id=? ORDER BY id LIMIT 1", (spotify_id,))
        if row:
            return row
    return await _one("SELECT * FROM tracks WHERE cache_key=?", (cache_key,))


async def get_track_by_id(track_id: int) -> dict | None:
    return await _one("SELECT * FROM tracks WHERE id=?", (track_id,))


async def get_track_by_spotify_id(spotify_id: str) -> dict | None:
    return await _one("SELECT * FROM tracks WHERE spotify_id=? ORDER BY id LIMIT 1", (spotify_id,))


async def save_track(*, cache_key: str, spotify_id: str | None, artist: str, title: str,
                     album: str | None, cover_url: str | None, duration: int | None,
                     file_id: str) -> int:
    await _c().execute(
        """INSERT INTO tracks(cache_key, spotify_id, artist, title, album, cover_url,
                              duration, file_id, search_text)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(cache_key) DO UPDATE SET file_id=excluded.file_id,
               spotify_id=COALESCE(excluded.spotify_id, tracks.spotify_id)""",
        (cache_key, spotify_id, artist, title, album, cover_url, duration, file_id,
         normalize_key(f"{artist} {title}")),
    )
    await _c().commit()
    row = await _one("SELECT id FROM tracks WHERE cache_key=?", (cache_key,))
    return row["id"]


async def search_tracks(query: str, limit: int = 5) -> list[dict]:
    words = [w for w in normalize_key(query).split() if w][:6]
    if not words:
        return []
    cond = " AND ".join("search_text LIKE ?" for _ in words)
    params = tuple(f"%{w}%" for w in words) + (limit,)
    return await _all(f"SELECT * FROM tracks WHERE {cond} ORDER BY downloads DESC, id DESC LIMIT ?", params)


async def top_tracks(limit: int = 10) -> list[dict]:
    return await _all("SELECT * FROM tracks ORDER BY downloads DESC, id DESC LIMIT ?", (limit,))


async def register_download(user_id: int, track_id: int) -> None:
    await _c().execute("UPDATE tracks SET downloads = downloads + 1 WHERE id=?", (track_id,))
    await _c().execute("INSERT INTO downloads(user_id, track_id) VALUES(?,?)", (user_id, track_id))
    await _c().commit()


# --- Statistika -------------------------------------------------------------
async def stats() -> dict:
    return {
        "users": await _scalar("SELECT COUNT(*) FROM users"),
        "active_today": await _scalar("SELECT COUNT(*) FROM users WHERE date(last_active) = date('now')"),
        "tracks": await _scalar("SELECT COUNT(*) FROM tracks"),
        "downloads": await _scalar("SELECT COUNT(*) FROM downloads"),
    }
