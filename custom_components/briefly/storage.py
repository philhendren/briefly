"""Persistent cache: summaries, seen stories and blocked sites."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    BLOCK_DURATION,
    CACHE_RETENTION,
    STATUS_DONE,
    STATUS_FEED_ONLY,
    STORAGE_KEY,
    STORAGE_VERSION,
)

SAVE_DELAY = 10


class SummaryRecord(TypedDict, total=False):
    """A cached summary outcome for one story."""

    status: str
    summary: list[str]
    key_facts: list[str]
    attempts: int
    reason: str
    updated: str


class BrieflyCache:
    """Cache for one news desk, kept in `.storage/briefly_cache.<entry_id>`."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the cache."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}"
        )
        self.summaries: dict[str, SummaryRecord] = {}
        self.seen: dict[str, str] = {}
        self.blocked: dict[str, str] = {}

    async def async_load(self) -> None:
        """Load the cache from disk."""
        data = await self._store.async_load() or {}
        self.summaries = data.get("summaries", {})
        self.seen = data.get("seen", {})
        self.blocked = data.get("blocked", {})

    def _data(self) -> dict[str, Any]:
        return {"summaries": self.summaries, "seen": self.seen, "blocked": self.blocked}

    def schedule_save(self) -> None:
        """Save soon, coalescing bursts of changes."""
        self._store.async_delay_save(self._data, SAVE_DELAY)

    async def async_save(self) -> None:
        """Save now."""
        await self._store.async_save(self._data())

    async def async_remove(self) -> None:
        """Delete the cache file."""
        await self._store.async_remove()

    # Seen stories -----------------------------------------------------------
    @property
    def has_history(self) -> bool:
        """Return True once at least one refresh has been recorded."""
        return bool(self.seen)

    def is_seen(self, story_id: str) -> bool:
        """Return True if the story was listed before."""
        return story_id in self.seen

    def mark_seen(self, story_id: str, now: datetime) -> None:
        """Record that the story was listed."""
        self.seen.setdefault(story_id, now.isoformat())

    # Summaries --------------------------------------------------------------
    def get_summary(self, story_id: str) -> SummaryRecord | None:
        """Return the cached summary outcome for a story."""
        return self.summaries.get(story_id)

    def set_done(self, story_id: str, summary: list[str], key_facts: list[str]) -> None:
        """Store a finished summary."""
        self.summaries[story_id] = SummaryRecord(
            status=STATUS_DONE,
            summary=summary,
            key_facts=key_facts,
            updated=dt_util.utcnow().isoformat(),
        )

    def set_feed_only(self, story_id: str, reason: str) -> None:
        """Record that this story will show its feed description only."""
        self.summaries[story_id] = SummaryRecord(
            status=STATUS_FEED_ONLY,
            reason=reason,
            updated=dt_util.utcnow().isoformat(),
        )

    def add_attempt(self, story_id: str) -> int:
        """Record a failed attempt and return the attempt count."""
        record = self.summaries.setdefault(story_id, SummaryRecord())
        record["attempts"] = record.get("attempts", 0) + 1
        record["updated"] = dt_util.utcnow().isoformat()
        return record["attempts"]

    # Blocked sites ----------------------------------------------------------
    def block_host(self, host: str, now: datetime) -> None:
        """Mark a site as feed-only for the block duration."""
        self.blocked[host] = (now + BLOCK_DURATION).isoformat()

    def host_blocked(self, host: str, now: datetime) -> bool:
        """Return True if article fetching is paused for this site."""
        if (until := self.blocked.get(host)) is None:
            return False
        if dt_util.parse_datetime(until) > now:
            return True
        del self.blocked[host]
        return False

    # Housekeeping -----------------------------------------------------------
    def prune(self, now: datetime, keep: set[str]) -> None:
        """Forget stories older than the retention period that are not listed."""
        cutoff = now - CACHE_RETENTION
        for story_id, first_seen in list(self.seen.items()):
            if story_id not in keep and dt_util.parse_datetime(first_seen) < cutoff:
                del self.seen[story_id]
                self.summaries.pop(story_id, None)
        for story_id in list(self.summaries):
            if story_id not in self.seen and story_id not in keep:
                del self.summaries[story_id]
