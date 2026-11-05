import os
import re
import time

import aiosqlite

import config

_db: aiosqlite.Connection | None = None


async def init() -> None:
    global _db
    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    _db = await aiosqlite.connect(config.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id   INTEGER PRIMARY KEY,
            username  TEXT,
            full_name TEXT,
            joined_at INTEGER NOT NULL,
            active    INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS tracks (
            key        TEXT PRIMARY KEY,
            title      TEXT NOT NULL,
            artist     TEXT NOT NULL,
            search     TEXT NOT NULL,
            duration   INTEGER,
            file_id    TEXT NOT NULL,
            plays      INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tracks_plays ON tracks(plays DESC);
        CREATE TABLE IF NOT EXISTS links (
            url        TEXT PRIMARY KEY,
            track_key  TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    await _db.commit()


async def close() -> None:
    if _db:
        await _db.close()


# ---------- foydalanuvchilar ----------
async def add_user(user_id: int, username: str | None, full_name: str) -> None:
    await _db.execute(
        """INSERT INTO users (user_id, username, full_name, joined_at, active)
           VALUES (?, ?, ?, ?, 1)
           ON CONFLICT(user_id) DO UPDATE SET
               username=excluded.username, full_name=excluded.full_name, active=1""",
        (user_id, username, full_name, int(time.time())),
    )
    await _db.commit()


async def set_inactive(user_id: int) -> None:
    await _db.execute("UPDATE users SET active=0 WHERE user_id=?", (user_id,))
    await _db.commit()


async def _scalar(sql: str, params: tuple = ()) -> int:
    cur = await _db.execute(sql, params)
    return (await cur.fetchone())[0]


async def count_users() -> int:
    return await _scalar("SELECT COUNT(*) FROM users")


async def count_active_users() -> int:
    return await _scalar("SELECT COUNT(*) FROM users WHERE active=1")


async def count_new_today() -> int:
    start = int(time.time()) // 86400 * 86400
    return await _scalar("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (start,))


async def get_active_user_ids() -> list[int]:
    cur = await _db.execute("SELECT user_id FROM users WHERE active=1")
    return [r[0] for r in await cur.fetchall()]


# ---------- file_id kesh ----------
async def get_track(key: str):
    cur = await _db.execute("SELECT * FROM tracks WHERE key=?", (key,))
    return await cur.fetchone()


async def get_tracks(keys: list[str]) -> dict[str, aiosqlite.Row]:
    if not keys:
        return {}
    marks = ",".join("?" * len(keys))
    cur = await _db.execute(f"SELECT * FROM tracks WHERE key IN ({marks})", keys)
    return {r["key"]: r for r in await cur.fetchall()}


async def save_track(key: str, title: str, artist: str, duration: int | None, file_id: str) -> None:
    await _db.execute(
        """INSERT INTO tracks (key, title, artist, search, duration, file_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET file_id=excluded.file_id""",
        (key, title, artist, f"{artist} {title}".lower(), duration, file_id, int(time.time())),
    )
    await _db.commit()


async def delete_track(key: str) -> None:
    await _db.execute("DELETE FROM tracks WHERE key=?", (key,))
    await _db.commit()


async def inc_plays(key: str) -> None:
    await _db.execute("UPDATE tracks SET plays = plays + 1 WHERE key=?", (key,))
    await _db.commit()


async def search_tracks(query: str, limit: int = 10):
    """Bazadagi (kesh) qo'shiqlar ichidan qidirish. Bir xil file_id bir marta chiqadi."""
    words = re.findall(r"\w+", query.lower())
    if not words:
        return []
    cond = " AND ".join(["search LIKE ? ESCAPE '\\'"] * len(words))
    params = [f"%{w.replace(chr(92), chr(92) * 2).replace('%', chr(92) + '%').replace('_', chr(92) + '_')}%" for w in words]
    cur = await _db.execute(
        f"SELECT *, MAX(plays) AS p FROM tracks WHERE {cond} GROUP BY file_id ORDER BY p DESC LIMIT ?",
        (*params, limit),
    )
    return await cur.fetchall()


async def top_tracks(limit: int = 30):
    cur = await _db.execute(
        "SELECT *, MAX(plays) AS p FROM tracks GROUP BY file_id ORDER BY p DESC, created_at DESC LIMIT ?",
        (limit,),
    )
    return await cur.fetchall()


async def count_tracks() -> int:
    return await _scalar("SELECT COUNT(DISTINCT file_id) FROM tracks")


async def total_plays() -> int:
    return await _scalar("SELECT COALESCE(SUM(plays), 0) FROM tracks")


# ---------- havola -> qo'shiq keshi ----------
async def get_link(url: str) -> str | None:
    cur = await _db.execute("SELECT track_key FROM links WHERE url=?", (url,))
    row = await cur.fetchone()
    return row[0] if row else None


async def set_link(url: str, track_key: str) -> None:
    await _db.execute(
        "INSERT INTO links (url, track_key, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(url) DO UPDATE SET track_key=excluded.track_key",
        (url, track_key, int(time.time())),
    )
    await _db.commit()
