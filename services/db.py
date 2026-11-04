import json
import time
from pathlib import Path
from typing import Optional

import aiosqlite

import config


class Database:
    def __init__(self) -> None:
        self.conn: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(config.DB_PATH)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                joined_at   INTEGER NOT NULL,
                last_active INTEGER NOT NULL,
                blocked     INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tracks (
                key        TEXT PRIMARY KEY,
                file_id    TEXT NOT NULL,
                title      TEXT,
                artist     TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS links (
                url       TEXT PRIMARY KEY,
                track_key TEXT NOT NULL
            );
            """
        )
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    # ---- users ----
    async def upsert_user(self, user_id: int, username: Optional[str], full_name: str) -> None:
        now = int(time.time())
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, full_name, joined_at, last_active, blocked)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                last_active=excluded.last_active,
                blocked=0
            """,
            (user_id, username, full_name, now, now),
        )
        await self.conn.commit()

    async def all_user_ids(self) -> list[int]:
        async with self.conn.execute("SELECT user_id FROM users WHERE blocked=0") as cur:
            return [r["user_id"] for r in await cur.fetchall()]

    async def mark_blocked(self, user_id: int) -> None:
        await self.conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (user_id,))
        await self.conn.commit()

    async def stats(self) -> dict:
        day_ago = int(time.time()) - 86400
        q = {
            "total": "SELECT COUNT(*) FROM users",
            "blocked": "SELECT COUNT(*) FROM users WHERE blocked=1",
            "active_24h": f"SELECT COUNT(*) FROM users WHERE last_active>{day_ago}",
            "new_24h": f"SELECT COUNT(*) FROM users WHERE joined_at>{day_ago}",
            "tracks": "SELECT COUNT(*) FROM tracks",
        }
        out = {}
        for name, sql in q.items():
            async with self.conn.execute(sql) as cur:
                out[name] = (await cur.fetchone())[0]
        return out

    # ---- tracks cache ----
    async def get_track(self, key: str) -> Optional[dict]:
        async with self.conn.execute("SELECT * FROM tracks WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def save_track(self, key: str, file_id: str, title: str, artist: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO tracks (key, file_id, title, artist, created_at) VALUES (?,?,?,?,?)",
            (key, file_id, title, artist, int(time.time())),
        )
        await self.conn.commit()

    async def get_link(self, url: str) -> Optional[str]:
        async with self.conn.execute("SELECT track_key FROM links WHERE url=?", (url,)) as cur:
            row = await cur.fetchone()
            return row["track_key"] if row else None

    async def save_link(self, url: str, track_key: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO links (url, track_key) VALUES (?,?)", (url, track_key)
        )
        await self.conn.commit()

    # ---- settings ----
    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        await self.conn.commit()

    async def get_channels(self) -> list[str]:
        raw = await self.get_setting("channels")
        if raw is None:  # birinchi ishga tushish: .env dagi kanallar
            await self.set_channels(list(config.CHANNELS))
            return list(config.CHANNELS)
        try:
            return list(json.loads(raw))
        except Exception:
            return []

    async def set_channels(self, channels: list[str]) -> None:
        await self.set_setting("channels", json.dumps(channels))

    async def clear_tracks(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM tracks") as cur:
            n = (await cur.fetchone())[0]
        await self.conn.execute("DELETE FROM tracks")
        await self.conn.execute("DELETE FROM links")
        await self.conn.commit()
        return n


db = Database()
