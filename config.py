"""Tizim konfiguratsiyasi (faqat environment variables orqali)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Union

ChannelId = Union[int, str]


def _parse_channels(raw: str) -> list[ChannelId]:
    """'@kanal1, -1001234567890, kanal2' -> ['@kanal1', -1001234567890, '@kanal2']"""
    channels: list[ChannelId] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if item.lstrip("-").isdigit():
            channels.append(int(item))
        elif item.startswith("https://t.me/"):
            channels.append("@" + item.rsplit("/", 1)[-1])
        elif item.startswith("@"):
            channels.append(item)
        else:
            channels.append("@" + item)
    return channels


@dataclass(frozen=True)
class Config:
    bot_token: str
    redis_url: str
    sponsor_channels: list[ChannelId] = field(default_factory=list)
    user_agent: str = "mcpe-discovery-bot/1.0 (github.com/your-org/mcpe-discovery-bot)"
    search_cache_ttl: int = 600
    download_cache_ttl: int = 900
    rate_limit_requests: int = 6      # oynada ruxsat etilgan so'rovlar soni
    rate_limit_window: int = 5        # oyna uzunligi (soniya)
    search_limit: int = 6


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi o'rnatilmagan.")

    return Config(
        bot_token=token,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(),
        sponsor_channels=_parse_channels(os.getenv("SPONSOR_CHANNELS", "")),
        user_agent=os.getenv(
            "MODRINTH_USER_AGENT",
            "mcpe-discovery-bot/1.0 (github.com/your-org/mcpe-discovery-bot)",
        ),
        search_cache_ttl=int(os.getenv("SEARCH_CACHE_TTL", "600")),
        download_cache_ttl=int(os.getenv("DOWNLOAD_CACHE_TTL", "900")),
        rate_limit_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "6")),
        rate_limit_window=int(os.getenv("RATE_LIMIT_WINDOW", "5")),
        search_limit=int(os.getenv("SEARCH_LIMIT", "6")),
    )
