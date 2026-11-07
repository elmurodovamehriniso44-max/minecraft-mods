"""SQLite ulanishi, sxema va xavfsiz yozish yordamchilari (aiosqlite)."""
import asyncio
import logging
from typing import Any, Optional, Sequence

import aiosqlite

import config

log = logging.getLogger(__name__)

_conn: Optional[aiosqlite.Connection] = None
_write_lock = asyncio.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    mc_version  TEXT,
    joined_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    emoji       TEXT NOT NULL DEFAULT '📦',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mods (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    preview_file_id  TEXT,
    file_id          TEXT NOT NULL,
    file_unique_id   TEXT,
    file_name        TEXT NOT NULL DEFAULT '',
    file_size        INTEGER NOT NULL DEFAULT 0,
    file_type        TEXT NOT NULL DEFAULT '',
    versions         TEXT NOT NULL DEFAULT '',
    author           TEXT NOT NULL DEFAULT '',
    category_id      INTEGER NOT NULL REFERENCES categories(id),
    downloads        INTEGER NOT NULL DEFAULT 0,
    instructions     TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id   INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    mod_id    INTEGER NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
    added_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, mod_id)
);

CREATE TABLE IF NOT EXISTS downloads (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    mod_id         INTEGER NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
    downloaded_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mod_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    normalized  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected','completed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mods_category   ON mods(category_id);
CREATE INDEX IF NOT EXISTS idx_mods_downloads  ON mods(downloads DESC);
CREATE INDEX IF NOT EXISTS idx_mods_name       ON mods(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_fav_mod         ON favorites(mod_id);
CREATE INDEX IF NOT EXISTS idx_dl_mod          ON downloads(mod_id);
CREATE INDEX IF NOT EXISTS idx_dl_user         ON downloads(user_id);
CREATE INDEX IF NOT EXISTS idx_dl_time         ON downloads(downloaded_at);
CREATE INDEX IF NOT EXISTS idx_req_status      ON mod_requests(status);
CREATE INDEX IF NOT EXISTS idx_req_user        ON mod_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_req_norm        ON mod_requests(normalized);
"""


async def init_db() -> None:
    """Bazani ochadi, jadvallarni yaratadi va kategoriyalarni to'ldiradi."""
    global _conn
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(str(config.DB_PATH))
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA foreign_keys = ON")
    await _conn.execute("PRAGMA journal_mode = WAL")
    await _conn.execute("PRAGMA synchronous = NORMAL")
    await _conn.executescript(SCHEMA)
    await _conn.executemany(
        "INSERT OR IGNORE INTO categories (name, emoji, sort_order) VALUES (?, ?, ?)",
        [(name, emoji, i) for i, (name, emoji) in enumerate(config.CATEGORIES, 1)],
    )
    await _conn.commit()
    log.info("Ma'lumotlar bazasi tayyor: %s", config.DB_PATH)


async def close_db() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


def _connection() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("Ma'lumotlar bazasi ishga tushirilmagan (init_db chaqirilmagan).")
    return _conn


async def fetch_all(sql: str, params: Sequence[Any] = ()) -> list:
    async with _connection().execute(sql, tuple(params)) as cur:
        return list(await cur.fetchall())


async def fetch_one(sql: str, params: Sequence[Any] = ()):
    async with _connection().execute(sql, tuple(params)) as cur:
        return await cur.fetchone()


async def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Bitta yozish amali. lastrowid qaytaradi."""
    conn = _connection()
    async with _write_lock:
        try:
            async with conn.execute(sql, tuple(params)) as cur:
                last_id = cur.lastrowid
            await conn.commit()
            return last_id
        except Exception:
            await conn.rollback()
            raise


async def transaction(statements: Sequence[tuple]) -> None:
    """Bir nechta yozish amalini bitta tranzaksiyada bajaradi."""
    conn = _connection()
    async with _write_lock:
        try:
            for sql, params in statements:
                async with conn.execute(sql, tuple(params)):
                    pass
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
