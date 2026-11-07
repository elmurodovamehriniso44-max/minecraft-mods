"""Tizim konfiguratsiyasi (muhit o'zgaruvchilari orqali)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Union

Channel = Union[int, str]


def _parse_channels(raw: str) -> List[Channel]:
    channels: List[Channel] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if item.lstrip("-").isdigit():
            channels.append(int(item))
        else:
            channels.append(item if item.startswith("@") else f"@{item}")
    return channels


@dataclass(frozen=True)
class Config:
    bot_token: str
    redis_url: str = "redis://localhost:6379/0"
    sponsor_channels: List[Channel] = field(default_factory=list)

    # Qo'shimcha sozlamalar
    search_cache_ttl: int = 300
    version_cache_ttl: int = 600
    subscription_cache_ttl: int = 60
    rate_limit_requests: int = 8
    rate_limit_window: int = 10


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi o'rnatilmagan.")
    return Config(
        bot_token=token,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(),
        sponsor_channels=_parse_channels(os.getenv("SPONSOR_CHANNELS", "")),
    )
