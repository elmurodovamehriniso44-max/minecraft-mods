from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import config


def _make_engine():
    url = make_url(config.database_url)
    connect_args: dict = {}
    if url.drivername.startswith("postgres"):
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        url = url.set(drivername="postgresql+asyncpg", query=query)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = True
        connect_args["statement_cache_size"] = 0  # pgbouncer (Neon pooler) bilan mos
    elif url.drivername.startswith("sqlite"):
        url = url.set(drivername="sqlite+aiosqlite")
    return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)


engine = _make_engine()
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Mod(Base):
    __tablename__ = "mods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[str] = mapped_column(String(20), index=True)
    tags: Mapped[str] = mapped_column(Text, default="")
    photos: Mapped[str] = mapped_column(Text, default="")  # file_id lar vergul bilan
    file_id: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    @property
    def photo_list(self) -> list[str]:
        return [p for p in (self.photos or "").split(",") if p]

    @property
    def cover(self) -> str:
        return self.photo_list[0]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------- Foydalanuvchilar ----------
async def upsert_user(tg_user):
    async with Session() as s:
        obj = await s.get(User, tg_user.id)
        if obj:
            obj.username = tg_user.username
            obj.full_name = tg_user.full_name
        else:
            s.add(User(id=tg_user.id, username=tg_user.username, full_name=tg_user.full_name))
        await s.commit()


async def all_user_ids() -> list[int]:
    async with Session() as s:
        return list((await s.execute(select(User.id))).scalars().all())


# ---------- Modlar ----------
async def add_mod(**fields) -> Mod:
    async with Session() as s:
        mod = Mod(**fields)
        s.add(mod)
        await s.commit()
        return mod


async def get_mod(mod_id: int) -> Mod | None:
    async with Session() as s:
        return await s.get(Mod, mod_id)


async def update_mod(mod_id: int, **fields):
    async with Session() as s:
        mod = await s.get(Mod, mod_id)
        if mod:
            for k, v in fields.items():
                setattr(mod, k, v)
            await s.commit()


async def delete_mod(mod_id: int):
    async with Session() as s:
        mod = await s.get(Mod, mod_id)
        if mod:
            await s.delete(mod)
            await s.commit()


async def inc_downloads(mod_id: int):
    async with Session() as s:
        mod = await s.get(Mod, mod_id)
        if mod:
            mod.downloads += 1
            await s.commit()


async def list_versions(category: str) -> list[str]:
    async with Session() as s:
        rows = (await s.execute(select(Mod.version).where(Mod.category == category).distinct())).scalars().all()
    return sorted(rows, key=lambda v: [int(x) for x in re.findall(r"\d+", v)], reverse=True)


async def get_mod_at(category: str, version: str, idx: int):
    """(mod, total, idx) qaytaradi. idx aylanma (-1 = oxirgisi)."""
    conds = [Mod.category == category]
    if version != "all":
        conds.append(Mod.version == version)
    async with Session() as s:
        total = (await s.execute(select(func.count(Mod.id)).where(*conds))).scalar_one()
        if total == 0:
            return None, 0, 0
        idx %= total
        mod = (
            await s.execute(select(Mod).where(*conds).order_by(Mod.id.desc()).offset(idx).limit(1))
        ).scalar_one()
    return mod, total, idx


async def search_mods(query: str, limit: int = 10) -> list[Mod]:
    words = [w.replace("%", "").replace("_", "") for w in query.lower().replace("#", " ").split()][:5]
    words = [w for w in words if w]
    if not words:
        return []
    conds = []
    for w in words:
        like = f"%{w}%"
        conds.append(
            or_(
                func.lower(Mod.title).like(like),
                func.lower(Mod.description).like(like),
                func.lower(Mod.tags).like(like),
                func.lower(Mod.version).like(like),
            )
        )
    async with Session() as s:
        res = await s.execute(select(Mod).where(*conds).order_by(Mod.downloads.desc()).limit(limit))
        return list(res.scalars().all())


async def list_mods_page(page: int, per: int = 8):
    async with Session() as s:
        total = (await s.execute(select(func.count(Mod.id)))).scalar_one()
        rows = (
            await s.execute(select(Mod).order_by(Mod.id.desc()).offset(page * per).limit(per))
        ).scalars().all()
    return list(rows), total


async def get_stats():
    async with Session() as s:
        users = (await s.execute(select(func.count(User.id)))).scalar_one()
        mods = (await s.execute(select(func.count(Mod.id)))).scalar_one()
        downloads = (await s.execute(select(func.coalesce(func.sum(Mod.downloads), 0)))).scalar_one()
        top = (await s.execute(select(Mod).order_by(Mod.downloads.desc()).limit(10))).scalars().all()
    return users, mods, downloads, list(top)
