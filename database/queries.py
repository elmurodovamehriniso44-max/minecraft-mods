"""Barcha SQL so'rovlari (parametrlashtirilgan, xavfsiz)."""
import math
from typing import Any, Iterable, Optional

import aiosqlite

import config
from database import db

_MOD_SELECT = (
    "SELECT m.*, c.name AS category_name, c.emoji AS category_emoji "
    "FROM mods m JOIN categories c ON c.id = m.category_id"
)

_MOD_EDITABLE = {
    "name", "description", "author", "instructions",
    "category_id", "versions", "preview_file_id",
}


# ------------------------------------------------------------------ users
async def upsert_user(user_id: int, username: Optional[str], full_name: str) -> None:
    await db.execute(
        """INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               full_name = excluded.full_name,
               last_seen = datetime('now')""",
        (user_id, username, full_name),
    )


async def get_user_version(user_id: int) -> Optional[str]:
    row = await db.fetch_one("SELECT mc_version FROM users WHERE user_id = ?", (user_id,))
    return row["mc_version"] if row and row["mc_version"] else None


async def set_user_version(user_id: int, version: Optional[str]) -> None:
    await db.execute("UPDATE users SET mc_version = ? WHERE user_id = ?", (version, user_id))


# ------------------------------------------------------------- categories
async def get_categories() -> list:
    return await db.fetch_all("SELECT * FROM categories ORDER BY sort_order, id")


async def get_categories_with_counts() -> list:
    return await db.fetch_all(
        """SELECT c.*, COUNT(m.id) AS mods_count
           FROM categories c LEFT JOIN mods m ON m.category_id = c.id
           GROUP BY c.id ORDER BY c.sort_order, c.id"""
    )


async def get_category(category_id: int):
    return await db.fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))


# ------------------------------------------------------------------- mods
async def add_mod(
    name: str, description: str, category_id: int, author: str, versions: str,
    preview_file_id: Optional[str], file_id: str, file_unique_id: str,
    file_name: str, file_size: int, file_type: str, instructions: str,
) -> int:
    return await db.execute(
        """INSERT INTO mods (name, description, category_id, author, versions,
                             preview_file_id, file_id, file_unique_id, file_name,
                             file_size, file_type, instructions)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, description, category_id, author, versions, preview_file_id,
         file_id, file_unique_id, file_name, file_size, file_type, instructions),
    )


async def get_mod(mod_id: int):
    return await db.fetch_one(f"{_MOD_SELECT} WHERE m.id = ?", (mod_id,))


async def get_mods_by_ids(ids: list) -> list:
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = await db.fetch_all(f"{_MOD_SELECT} WHERE m.id IN ({placeholders})", ids)
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


async def update_mod_field(mod_id: int, field: str, value: Any) -> None:
    if field not in _MOD_EDITABLE:
        raise ValueError(f"Ruxsat etilmagan maydon: {field}")
    await db.execute(f"UPDATE mods SET {field} = ? WHERE id = ?", (value, mod_id))


async def update_mod_file(
    mod_id: int, file_id: str, file_unique_id: str, file_name: str, file_size: int, file_type: str
) -> None:
    await db.execute(
        """UPDATE mods SET file_id = ?, file_unique_id = ?, file_name = ?,
                           file_size = ?, file_type = ? WHERE id = ?""",
        (file_id, file_unique_id, file_name, file_size, file_type, mod_id),
    )


async def delete_mod(mod_id: int) -> None:
    await db.execute("DELETE FROM mods WHERE id = ?", (mod_id,))


async def list_mods(kind: str, arg: int, page: int, user_id: int = 0, version: Optional[str] = None):
    """Sahifalangan ro'yxat. (rows, total, to'g'rilangan_sahifa) qaytaradi."""
    joins = ""
    where = []
    params: list = []
    order = "m.name COLLATE NOCASE ASC"

    if kind == "fav":
        joins = " JOIN favorites f ON f.mod_id = m.id"
        where.append("f.user_id = ?")
        params.append(user_id)
        order = "f.added_at DESC"
    elif kind == "cat":
        where.append("m.category_id = ?")
        params.append(arg)
    elif kind == "ver":
        if not version or version not in config.MC_VERSIONS:
            return [], 0, 0
        where.append("(',' || m.versions || ',') LIKE ?")
        params.append(f"%,{version},%")
    elif kind == "pop":
        order = "m.downloads DESC, m.id DESC"
    elif kind == "new":
        order = "m.id DESC"

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    count_row = await db.fetch_one(f"SELECT COUNT(*) AS n FROM mods m{joins}{where_sql}", params)
    total = count_row["n"]
    pages = max(1, math.ceil(total / config.PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = await db.fetch_all(
        f"{_MOD_SELECT}{joins}{where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [config.PAGE_SIZE, page * config.PAGE_SIZE],
    )
    return rows, total, page


async def search_index() -> list:
    """Qidiruv uchun yengil indeks (butun katalog xotirada tez skanerlanadi)."""
    return await db.fetch_all(
        """SELECT m.id, m.name, m.description, m.author, m.versions, m.category_id,
                  m.downloads, c.name AS category_name
           FROM mods m JOIN categories c ON c.id = m.category_id"""
    )


# -------------------------------------------------------------- favorites
async def is_favorite(user_id: int, mod_id: int) -> bool:
    row = await db.fetch_one(
        "SELECT 1 FROM favorites WHERE user_id = ? AND mod_id = ?", (user_id, mod_id)
    )
    return row is not None


async def toggle_favorite(user_id: int, mod_id: int) -> bool:
    """Yangi holatni qaytaradi: True — sevimlilarda, False — yo'q."""
    if await is_favorite(user_id, mod_id):
        await db.execute("DELETE FROM favorites WHERE user_id = ? AND mod_id = ?", (user_id, mod_id))
        return False
    try:
        await db.execute("INSERT OR IGNORE INTO favorites (user_id, mod_id) VALUES (?, ?)", (user_id, mod_id))
    except aiosqlite.IntegrityError:
        return False
    return True


# -------------------------------------------------------------- downloads
async def record_download(user_id: int, mod_id: int) -> None:
    try:
        await db.transaction([
            ("INSERT INTO downloads (user_id, mod_id) VALUES (?, ?)", (user_id, mod_id)),
            ("UPDATE mods SET downloads = downloads + 1 WHERE id = ?", (mod_id,)),
        ])
    except aiosqlite.IntegrityError:
        pass  # mod yuklash paytida o'chirilgan bo'lishi mumkin


# --------------------------------------------------------------- requests
async def count_user_requests_since(user_id: int, modifier: str) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM mod_requests WHERE user_id = ? AND created_at >= datetime('now', ?)",
        (user_id, modifier),
    )
    return row["n"]


async def find_exact_duplicate(normalized: str) -> bool:
    row = await db.fetch_one(
        "SELECT id FROM mod_requests WHERE normalized = ? AND status != 'rejected' LIMIT 1",
        (normalized,),
    )
    return row is not None


async def recent_normalized(limit: int = 100) -> list:
    rows = await db.fetch_all(
        "SELECT normalized FROM mod_requests WHERE status IN ('pending', 'approved') "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [r["normalized"] for r in rows]


async def add_request(user_id: int, text: str, normalized: str) -> int:
    return await db.execute(
        "INSERT INTO mod_requests (user_id, text, normalized) VALUES (?, ?, ?)",
        (user_id, text, normalized),
    )


async def list_user_requests(user_id: int, limit: int = 5) -> list:
    return await db.fetch_all(
        "SELECT * FROM mod_requests WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
    )


async def get_request(request_id: int):
    return await db.fetch_one(
        """SELECT r.*, u.username, u.full_name
           FROM mod_requests r JOIN users u ON u.user_id = r.user_id
           WHERE r.id = ?""",
        (request_id,),
    )


async def list_requests(status: str, page: int):
    count_row = await db.fetch_one("SELECT COUNT(*) AS n FROM mod_requests WHERE status = ?", (status,))
    total = count_row["n"]
    pages = max(1, math.ceil(total / config.PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = await db.fetch_all(
        "SELECT * FROM mod_requests WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (status, config.PAGE_SIZE, page * config.PAGE_SIZE),
    )
    return rows, total, page


async def set_request_status(request_id: int, status: str) -> None:
    if status not in config.REQUEST_STATUSES:
        raise ValueError("Noto'g'ri holat")
    await db.execute("UPDATE mod_requests SET status = ? WHERE id = ?", (status, request_id))


# ------------------------------------------------------------------ stats
async def get_stats() -> dict:
    async def scalar(sql: str, params: Iterable = ()) -> int:
        row = await db.fetch_one(sql, tuple(params))
        return row["n"] or 0

    stats = {
        "users": await scalar("SELECT COUNT(*) AS n FROM users"),
        "mods": await scalar("SELECT COUNT(*) AS n FROM mods"),
        "downloads": await scalar("SELECT COALESCE(SUM(downloads), 0) AS n FROM mods"),
        "today": await scalar(
            "SELECT COUNT(*) AS n FROM downloads WHERE downloaded_at >= datetime('now', 'start of day')"
        ),
        "week": await scalar(
            "SELECT COUNT(*) AS n FROM downloads WHERE downloaded_at >= datetime('now', '-7 days')"
        ),
        "favorites": await scalar("SELECT COUNT(*) AS n FROM favorites"),
        "pending": await scalar("SELECT COUNT(*) AS n FROM mod_requests WHERE status = 'pending'"),
    }
    stats["top"] = await db.fetch_all(
        "SELECT id, name, downloads FROM mods ORDER BY downloads DESC, id DESC LIMIT 10"
    )
    return stats
