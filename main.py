"""Botni ishga tushirish."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from redis.asyncio import Redis

from config import load_config
from handlers import router
from modrinth_service import ModrinthPEService
from subscription_middleware import SponsorshipCheckMiddleware, ThrottlingMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("main")

    cfg = load_config()

    redis = Redis.from_url(cfg.redis_url)
    await redis.ping()  # Redis mavjudligini boshida tekshiramiz
    logger.info("Redis ulandi")

    storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(prefix="mcpe_fsm"))
    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher(storage=storage)

    service = ModrinthPEService(
        user_agent=cfg.user_agent,
        redis=redis,
        search_cache_ttl=cfg.search_cache_ttl,
        download_cache_ttl=cfg.download_cache_ttl,
    )

    # Handlerlarga dependency injection orqali uzatiladigan obyektlar
    dp["redis"] = redis
    dp["service"] = service
    dp["search_limit"] = cfg.search_limit

    # Tartib: avval tezlik cheklovi, keyin majburiy obuna
    throttle = ThrottlingMiddleware(
        redis, limit=cfg.rate_limit_requests, window=cfg.rate_limit_window
    )
    sponsor = SponsorshipCheckMiddleware(cfg.sponsor_channels, redis=redis)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)
        observer.outer_middleware(sponsor)

    dp.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Polling boshlandi")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await service.close()
        await storage.close()
        await redis.aclose()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger("main").info("Bot to'xtatildi")
