"""Modrinth V2 API uchun asinxron servis (faqat Bedrock/PE kontenti)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.modrinth.com/v2/"

# Majburiy filtr: Java fayllari aralashib ketmasligi uchun.
PE_FACETS: list[list[str]] = [
    ["project_type:modpack", "categories:bedrock", "categories:addon"]
]

# Faqat Bedrock/PE formatlari. .jar kabi Java fayllar HECH QACHON qaytarilmaydi.
PE_FILE_EXTENSIONS: tuple[str, ...] = (
    ".mcaddon",
    ".mcpack",
    ".mcworld",
    ".mctemplate",
    ".zip",
)


class ModrinthAPIError(Exception):
    """Modrinth API bilan bog'liq xatolik."""


class ModrinthPEService:
    def __init__(
        self,
        user_agent: str,
        redis: Any = None,
        search_cache_ttl: int = 600,
        download_cache_ttl: int = 900,
        timeout: float = 15.0,
        max_connections: int = 100,
        max_retries: int = 3,
    ) -> None:
        self._redis = redis
        self._search_ttl = search_cache_ttl
        self._download_ttl = download_cache_ttl
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=httpx.Timeout(timeout, connect=8.0),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max(10, max_connections // 4),
            ),
            follow_redirects=True,
        )

    # ------------------------------------------------------------------ infra
    async def close(self) -> None:
        await self._client.aclose()

    async def _cache_get(self, key: str) -> Optional[Any]:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception:  # kesh xatosi asosiy oqimni to'xtatmasligi kerak
            logger.warning("Redis cache o'qishda xato: %s", key, exc_info=True)
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception:
            logger.warning("Redis cache yozishda xato: %s", key, exc_info=True)

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 429:
                    delay = float(resp.headers.get("Retry-After", 2 * attempt))
                    logger.warning("Modrinth 429, %.1fs kutiladi", delay)
                    await asyncio.sleep(min(delay, 10))
                    continue
                if resp.status_code >= 500:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * attempt)
        raise ModrinthAPIError(f"Modrinth API javob bermadi: {path}") from last_exc

    # ----------------------------------------------------------------- public
    async def search_pe_content(self, query: str, limit: int = 6) -> list[dict]:
        """Bedrock/PE kontentini qidiradi.

        Qaytaradi: [{"id", "name", "description", "icon_url", "project_type", "slug"}]
        """
        query = " ".join(query.split())[:100]
        if not query:
            return []

        digest = hashlib.sha1(query.lower().encode()).hexdigest()
        cache_key = f"mrpe:search:{digest}:{limit}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        params = {
            "query": query,
            "limit": limit,
            "index": "relevance",
            "facets": json.dumps(PE_FACETS, separators=(",", ":")),
        }
        data = await self._get("search", params=params)
        hits = (data or {}).get("hits", [])

        results = [
            {
                "id": hit["project_id"],
                "name": hit.get("title") or hit.get("slug") or "Nomsiz",
                "description": (hit.get("description") or "").strip(),
                "icon_url": hit.get("icon_url"),
                "project_type": hit.get("project_type", ""),
                "slug": hit.get("slug", ""),
            }
            for hit in hits
            if hit.get("project_id")
        ]
        await self._cache_set(cache_key, results, self._search_ttl)
        return results

    async def get_latest_pe_download(self, project_id: str) -> dict:
        """Loyihaning eng so'nggi PE faylini topadi.

        Qaytaradi (topilmasa bo'sh dict):
        {"name", "description", "icon_url", "version", "filename",
         "extension", "url", "size_mb", "project_url"}
        """
        cache_key = f"mrpe:dl:{project_id}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        project, versions = await asyncio.gather(
            self._get(f"project/{project_id}"),
            self._get(f"project/{project_id}/version"),
        )
        if not project or not versions:
            return {}

        # Eng yangisi birinchi bo'lishi uchun saralash (ISO sana leksikografik tartibda).
        versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)

        chosen_file: Optional[dict] = None
        chosen_version: Optional[dict] = None
        for version in versions:
            files = version.get("files") or []
            candidates = [
                f for f in files
                if str(f.get("filename", "")).lower().endswith(PE_FILE_EXTENSIONS)
            ]
            if not candidates:
                continue
            primary = [f for f in candidates if f.get("primary")]
            chosen_file = (primary or candidates)[0]
            chosen_version = version
            break

        if not chosen_file or not chosen_version:
            return {}

        filename = chosen_file["filename"]
        slug = project.get("slug") or project_id
        result = {
            "name": project.get("title") or slug,
            "description": (project.get("description") or "").strip(),
            "icon_url": project.get("icon_url"),
            "version": chosen_version.get("version_number")
            or chosen_version.get("name")
            or "—",
            "filename": filename,
            "extension": "." + filename.rsplit(".", 1)[-1].lower(),
            "url": chosen_file["url"],
            "size_mb": round((chosen_file.get("size") or 0) / (1024 * 1024), 2),
            "project_url": f"https://modrinth.com/project/{slug}",
        }
        await self._cache_set(cache_key, result, self._download_ttl)
        return result
