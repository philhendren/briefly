"""Serve story thumbnails through Home Assistant, cached on disk for 48 hours.

Dashboards then never contact third-party image servers directly, and images
still load when a CDN blocks hotlinking. The view only serves images for
stories Briefly currently lists, so it cannot be used as an open proxy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, IMAGE_CACHE_DIR, IMAGE_CACHE_TTL, IMAGE_URL


def _read_cached(path: Path, ttl: float) -> tuple[bytes, str] | None:
    meta = path.with_suffix(".json")
    if not path.exists() or not meta.exists():
        return None
    if time.time() - path.stat().st_mtime > ttl:
        return None
    content_type = json.loads(meta.read_text())["content_type"]
    return path.read_bytes(), content_type


def _write_cached(path: Path, body: bytes, content_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    path.with_suffix(".json").write_text(json.dumps({"content_type": content_type}))


def prune_image_cache(directory: Path, ttl: float) -> int:
    """Delete cached images older than the TTL; return how many were removed."""
    if not directory.is_dir():
        return 0
    removed = 0
    cutoff = time.time() - ttl
    for file in directory.iterdir():
        if file.stat().st_mtime < cutoff:
            file.unlink(missing_ok=True)
            removed += file.suffix != ".json"
    return removed


def image_cache_dir(hass: HomeAssistant) -> Path:
    """Return the image cache directory."""
    return Path(hass.config.path(IMAGE_CACHE_DIR))


class BrieflyImageView(HomeAssistantView):
    """Image proxy for story thumbnails."""

    url = IMAGE_URL
    name = f"api:{DOMAIN}:image"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the view."""
        self.hass = hass

    def _lookup(self, story_id: str, size: str) -> tuple[str | None, object | None]:
        for entry in self.hass.config_entries.async_loaded_entries(DOMAIN):
            coordinator = entry.runtime_data.coordinator
            if coordinator.data and (story := coordinator.data.find_story(story_id)):
                url = story.image_large if size == "large" else story.image_small
                return url, coordinator.http
        return None, None

    async def get(self, request: web.Request, story_id: str) -> web.StreamResponse:
        """Return the image for a listed story."""
        size = request.query.get("size", "small")
        url, http = self._lookup(story_id, size)
        if url is None or http is None:
            return web.Response(status=404)
        ttl = IMAGE_CACHE_TTL.total_seconds()
        path = (
            image_cache_dir(self.hass)
            / hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()
        )
        cached = await self.hass.async_add_executor_job(_read_cached, path, ttl)
        if cached is None:
            result = await http.fetch_image(url)
            if result is None:
                return web.Response(status=502)
            cached = (result.content, result.content_type)
            await self.hass.async_add_executor_job(
                _write_cached, path, result.content, result.content_type
            )
        body, content_type = cached
        return web.Response(
            body=body,
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
