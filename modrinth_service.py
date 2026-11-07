"""Modrinth V2 API uchun asinxron xizmat (Bedrock / PE kontenti)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

API_BASE = "https://api.modrinth.com/v2"
SITE_BASE = "https://modrinth.com"
USER_AGENT = "mc-pe-discovery-bot/1.0 (telegram bot)"

# Java fayllari aralashmasligi uchun Bedrock/addon filtri.
PE_FACETS = [["project_type:modpack", "categories:bedrock"], ["categories:addon"]]

PREFERRED_EXTENSIONS = (".mcaddon", ".mcpack", ".mcworld", ".mctemplate", ".zip")


class ModrinthError(Exception):
    """Modrinth API bilan ishlashdagi xatolik."""


class ModrinthPEService:
    def __init__(self, redis: Optional[Redis] = None,
                 search_ttl: int = 300, version_ttl: int = 600) -> None:
        self._redis = redis
        self._search_ttl = search_ttl
        self._version_ttl = version_ttl
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=httpx.Timeout(12.0, connect=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ cache
    async def _cache_get(self, key: str) -> Any:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # kesh xatosi asosiy oqimni to'xtatmasin
            logger.warning("Redis cache read failed: %s", exc)
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception as exc:
            logger.warning("Redis cache write failed: %s", exc)

    # ------------------------------------------------------------------- http
    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = float(resp.headers.get("Retry-After", 1))
                    await asyncio.sleep(min(retry_after, 3) * (attempt + 1))
                    last_exc = ModrinthError(f"HTTP {resp.status_code}")
                    continue
                if resp.status_code == 404:
                    raise ModrinthError("Topilmadi (404).")
                resp.raise_for_status()
                return resp.json()
            except ModrinthError:
                raise
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ModrinthError(f"Modrinth API ishlamadi: {last_exc}")

    # ------------------------------------------------------------------ public
    async def search_pe_content(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        query = query.strip()
        cache_key = f"modrinth:search:{limit}:{query.lower()}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        params = {
            "query": query,
            "facets": json.dumps(PE_FACETS, separators=(",", ":")),
            "limit": limit,
            "index": "relevance",
        }
        data = await self._get_json("/search", params=params)
        results = [
            {
                "title": hit.get("title") or "Nomsiz",
                "id": hit.get("project_id"),
                "description": hit.get("description") or "",
                "icon_url": hit.get("icon_url") or "",
            }
            for hit in data.get("hits", [])
            if hit.get("project_id")
        ]
        await self._cache_set(cache_key, results, self._search_ttl)
        return results

    async def get_project(self, project_id: str) -> Dict[str, Any]:
        cache_key = f"modrinth:project:{project_id}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = await self._get_json(f"/project/{project_id}")
        project = {
            "title": data.get("title") or "Nomsiz",
            "id": data.get("id") or project_id,
            "description": data.get("description") or "",
            "icon_url": data.get("icon_url") or "",
        }
        await self._cache_set(cache_key, project, self._version_ttl)
        return project

    async def get_latest_pe_download(self, project_id: str) -> Dict[str, Any]:
        """Eng so'nggi versiyaning to'g'ridan-to'g'ri CDN havolasi va hajmini qaytaradi.

        Fayl topilmasa bo'sh dict qaytadi.
        """
        cache_key = f"modrinth:download:{project_id}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        versions = await self._get_json(f"/project/{project_id}/version")
        if not isinstance(versions, list) or not versions:
            await self._cache_set(cache_key, {}, 60)
            return {}

        versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)

        def pick_file(version: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            files = version.get("files") or []
            if not files:
                return None
            preferred = [
                f for f in files
                if str(f.get("filename", "")).lower().endswith(PREFERRED_EXTENSIONS)
            ]
            pool = preferred or files
            primary = [f for f in pool if f.get("primary")]
            return (primary or pool)[0]

        chosen_version, chosen_file = None, None
        # 1) Avval Bedrock formatidagi fayli bor eng yangi versiya
        for v in versions:
            f = pick_file(v)
            if f and str(f.get("filename", "")).lower().endswith(PREFERRED_EXTENSIONS):
                chosen_version, chosen_file = v, f
                break
        # 2) Aks holda istalgan fayli bor eng yangi versiya
        if chosen_file is None:
            for v in versions:
                f = pick_file(v)
                if f:
                    chosen_version, chosen_file = v, f
                    break

        if chosen_file is None or chosen_version is None:
            await self._cache_set(cache_key, {}, 60)
            return {}

        size_bytes = int(chosen_file.get("size") or 0)
        result = {
            "url": chosen_file.get("url", ""),
            "filename": chosen_file.get("filename", "file"),
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "version_name": chosen_version.get("name") or "",
            "version_number": chosen_version.get("version_number") or "",
            "game_versions": chosen_version.get("game_versions") or [],
            "page_url": f"{SITE_BASE}/project/{project_id}",
        }
        await self._cache_set(cache_key, result, self._version_ttl)
        return result
