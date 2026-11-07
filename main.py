"""Botni ishga tushirish."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from config import load_config
from handlers import router
from modrinth_service import ModrinthPEService
from subscription_middleware import SponsorshipCheckMiddleware, ThrottlingMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    cfg = load_config()

    redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    await redis.ping()  # Redis mavjudligini boshlanishdayoq tekshiramiz

    storage = RedisStorage(redis=redis)
    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    service = ModrinthPEService(
        redis=redis,
        search_ttl=cfg.search_cache_ttl,
        version_ttl=cfg.version_cache_ttl,
    )
    dp["service"] = service

    throttle = ThrottlingMiddleware(
        redis, limit=cfg.rate_limit_requests, window=cfg.rate_limit_window
    )
    sponsor = SponsorshipCheckMiddleware(
        cfg.sponsor_channels, redis=redis, cache_ttl=cfg.subscription_cache_ttl
    )
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)
        observer.outer_middleware(sponsor)

    dp.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await service.close()
        await storage.close()
        await redis.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
