"""Polite HTTP access to feeds, articles, robots.txt and images."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import logging
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import aiohttp
from homeassistant.util import dt as dt_util

from .const import (
    BLOCK_STATUSES,
    HTTP_TIMEOUT,
    MAX_DOWNLOAD_BYTES,
    ROBOTS_AGENT,
    ROBOTS_TTL,
    USER_AGENT,
)
from .storage import BrieflyCache

_LOGGER = logging.getLogger(__name__)

FEED_OK = "ok"
FEED_NOT_MODIFIED = "not_modified"
FEED_ERROR = "error"

ARTICLE_OK = "ok"
ARTICLE_BLOCKED = "blocked"
ARTICLE_DISALLOWED = "disallowed"
ARTICLE_ERROR = "error"


@dataclass(slots=True)
class FetchResult:
    """The outcome of a request."""

    status: str
    content: bytes = b""
    content_type: str = ""
    error: str = ""


def host_of(url: str) -> str:
    """Return the lower-case host of a URL."""
    return (urlsplit(url).hostname or "").lower()


class BrieflyHttp:
    """HTTP client that follows Briefly's publisher etiquette."""

    def __init__(self, session: aiohttp.ClientSession, cache: BrieflyCache) -> None:
        """Initialise the client."""
        self._session = session
        self._cache = cache
        self._validators: dict[str, dict[str, str]] = {}
        self._robots: dict[str, tuple[datetime, RobotFileParser | None]] = {}

    async def _get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> tuple[int, bytes, Mapping[str, str]]:
        async with self._session.get(
            url,
            headers={"User-Agent": USER_AGENT, **(headers or {})},
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
        ) as resp:
            body = await resp.read() if resp.status == 200 else b""
            return resp.status, body, resp.headers

    async def fetch_feed(self, url: str) -> FetchResult:
        """Fetch a feed, using ETag / Last-Modified so unchanged feeds are cheap."""
        try:
            status, body, headers = await self._get(url, self._validators.get(url))
        except (aiohttp.ClientError, TimeoutError) as err:
            return FetchResult(FEED_ERROR, error=str(err) or type(err).__name__)
        if status == 304:
            return FetchResult(FEED_NOT_MODIFIED)
        if status != 200:
            return FetchResult(FEED_ERROR, error=f"HTTP {status}")
        validators = {}
        if etag := headers.get("ETag"):
            validators["If-None-Match"] = etag
        if modified := headers.get("Last-Modified"):
            validators["If-Modified-Since"] = modified
        self._validators[url] = validators
        return FetchResult(FEED_OK, content=body)

    async def _robots_parser(self, url: str, now: datetime) -> RobotFileParser | None:
        """Return the site's robots rules; None means 'do not fetch'."""
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(root)
        if cached and cached[0] > now:
            return cached[1]
        parser: RobotFileParser | None = RobotFileParser()
        try:
            status, body, _headers = await self._get(f"{root}/robots.txt")
        except aiohttp.ClientError, TimeoutError:
            # Unreachable: try again next time, fetch nothing meanwhile.
            return None
        if status == 200:
            parser.parse(body.decode("utf-8", errors="ignore").splitlines())
        elif 400 <= status < 500:
            parser.parse([])  # RFC 9309: no robots.txt means no restrictions
        else:
            parser = None  # RFC 9309: server error means assume disallowed
        self._robots[root] = (now + ROBOTS_TTL, parser)
        return parser

    async def allowed_by_robots(self, url: str) -> bool:
        """Return True if robots.txt lets Briefly fetch this URL."""
        parser = await self._robots_parser(url, dt_util.utcnow())
        return parser is not None and parser.can_fetch(ROBOTS_AGENT, url)

    def site_blocked(self, url: str) -> bool:
        """Return True if this site is in its feed-only period."""
        return self._cache.host_blocked(host_of(url), dt_util.utcnow())

    async def fetch_article(self, url: str) -> FetchResult:
        """Fetch an article page once, respecting robots.txt and refusals."""
        if self.site_blocked(url):
            return FetchResult(ARTICLE_BLOCKED)
        if not await self.allowed_by_robots(url):
            return FetchResult(ARTICLE_DISALLOWED)
        try:
            status, body, headers = await self._get(url)
        except (aiohttp.ClientError, TimeoutError) as err:
            return FetchResult(ARTICLE_ERROR, error=str(err) or type(err).__name__)
        if status in BLOCK_STATUSES:
            _LOGGER.info(
                "%s refused article fetching (HTTP %s); feed text only for 7 days",
                host_of(url),
                status,
            )
            self._cache.block_host(host_of(url), dt_util.utcnow())
            self._cache.schedule_save()
            return FetchResult(ARTICLE_BLOCKED, error=f"HTTP {status}")
        if status != 200:
            return FetchResult(ARTICLE_ERROR, error=f"HTTP {status}")
        content_type = headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            return FetchResult(ARTICLE_ERROR, error=f"Not HTML: {content_type}")
        return FetchResult(ARTICLE_OK, content=body[:MAX_DOWNLOAD_BYTES])

    async def fetch_image(self, url: str) -> FetchResult | None:
        """Fetch an image; None if it is unavailable or not an image."""
        try:
            status, body, headers = await self._get(url)
        except aiohttp.ClientError, TimeoutError:
            return None
        content_type = headers.get("Content-Type", "").split(";")[0].strip().lower()
        if status != 200 or not content_type.startswith("image/"):
            return None
        if len(body) > MAX_DOWNLOAD_BYTES:
            return None
        return FetchResult(ARTICLE_OK, content=body, content_type=content_type)
