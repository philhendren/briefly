"""The update coordinator: one refresh of one news desk."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COLOUR,
    CONF_CUSTOM_FEEDS,
    CONF_DEDUP,
    CONF_FEEDS,
    CONF_MAX_AGE_HOURS,
    CONF_REFRESH_MINUTES,
    CONF_SECTION_ID,
    CONF_SECTION_NAME,
    CONF_SECTIONS,
    CONF_STORIES_PER_SECTION,
    CONF_SUMMARIES_PER_REFRESH,
    DEDUP_THRESHOLDS,
    DEFAULT_COLOUR,
    DEFAULT_SETTINGS,
    DOMAIN,
    IMAGE_CACHE_TTL,
    MAX_SUMMARY_ATTEMPTS,
    MIN_ARTICLE_CHARS,
    STATUS_DONE,
    STATUS_FEED_ONLY,
    STATUS_OFF,
    STATUS_PENDING,
)
from .dedup import dedupe
from .extract import extract_article_text
from .feeds import FeedError, parse_feed
from .image_proxy import image_cache_dir, prune_image_cache
from .http import ARTICLE_OK, FEED_NOT_MODIFIED, FEED_OK, BrieflyHttp
from .models import BrieflyData, Section, Story
from .ollama import OllamaError, OllamaSummariser, numbers_supported
from .sources import PRESET_FEEDS
from .storage import BrieflyCache

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class FeedRef:
    """A feed URL and the publisher name to show for it."""

    url: str
    source: str | None


def section_feeds(section: dict[str, Any]) -> list[FeedRef]:
    """Return the feeds configured for a section."""
    refs = [
        FeedRef(PRESET_FEEDS[key].url, PRESET_FEEDS[key].source)
        for key in section.get(CONF_FEEDS, [])
        if key in PRESET_FEEDS
    ]
    refs.extend(FeedRef(url, None) for url in section.get(CONF_CUSTOM_FEEDS, []))
    return refs


class BrieflyCoordinator(DataUpdateCoordinator[BrieflyData]):
    """Fetch, sort, de-duplicate and (optionally) summarise news."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        cache: BrieflyCache,
        http: BrieflyHttp,
        summariser: OllamaSummariser | None,
    ) -> None:
        """Initialise the coordinator."""
        self.settings = {**DEFAULT_SETTINGS, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=self.settings[CONF_REFRESH_MINUTES]),
        )
        self.cache = cache
        self.http = http
        self.summariser = summariser
        self.section_config: list[dict[str, Any]] = list(entry.options.get(CONF_SECTIONS, []))
        self._feed_stories: dict[str, list[Story]] = {}
        self._summary_lock = asyncio.Lock()

    @property
    def summaries_enabled(self) -> bool:
        """Return True if summaries are switched on."""
        return self.summariser is not None

    # Refresh ----------------------------------------------------------------
    async def _fetch(self, ref: FeedRef) -> bool:
        """Fetch and parse one feed; return False on failure."""
        result = await self.http.fetch_feed(ref.url)
        if result.status == FEED_NOT_MODIFIED:
            return ref.url in self._feed_stories
        if result.status != FEED_OK:
            _LOGGER.warning("Could not fetch %s: %s", ref.url, result.error)
            return False
        try:
            parsed = await self.hass.async_add_executor_job(
                parse_feed, result.content, ref.source
            )
        except FeedError:
            _LOGGER.warning("%s is not a valid RSS or Atom feed", ref.url)
            return False
        self._feed_stories[ref.url] = parsed.stories
        return True

    async def _async_update_data(self) -> BrieflyData:
        """Fetch every feed and build the sections."""
        refs = {ref for section in self.section_config for ref in section_feeds(section)}
        outcomes = await asyncio.gather(*(self._fetch(ref) for ref in refs))
        errors = outcomes.count(False)
        if refs and errors == len(refs) and not self._feed_stories:
            raise UpdateFailed("None of the feeds could be fetched")

        now = dt_util.utcnow()
        data, candidates = self._build(now, errors)

        if self.cache.has_history:
            seen_new: set[str] = set()
            for section, story in data.all_stories():
                if not self.cache.is_seen(story.id) and story.id not in seen_new:
                    seen_new.add(story.id)
                    data.new_stories.append((section.id, story))
        # Every in-window story counts as seen, including duplicates folded away and
        # stories below the cut, so they never fire later as "new".
        for story_id in candidates:
            self.cache.mark_seen(story_id, now)
        self.cache.prune(now, candidates)
        self.cache.schedule_save()
        await self.hass.async_add_executor_job(
            prune_image_cache, image_cache_dir(self.hass), IMAGE_CACHE_TTL.total_seconds()
        )

        if self.summaries_enabled and data.count_status(STATUS_PENDING):
            self.config_entry.async_create_background_task(
                self.hass, self.async_summarise_pending(data), f"{DOMAIN} summaries"
            )
        return data

    def _build(self, now: Any, errors: int) -> tuple[BrieflyData, set[str]]:
        """Build fresh section data; also return every in-window story id."""
        candidates: set[str] = set()
        cutoff = now - timedelta(hours=self.settings[CONF_MAX_AGE_HOURS])
        threshold = DEDUP_THRESHOLDS.get(self.settings[CONF_DEDUP])
        limit = int(self.settings[CONF_STORIES_PER_SECTION])
        sections: dict[str, Section] = {}
        for config in self.section_config:
            stories: list[Story] = []
            for ref in section_feeds(config):
                stories.extend(
                    _copy(story)
                    for story in self._feed_stories.get(ref.url, [])
                    if story.published >= cutoff
                )
            candidates.update(story.id for story in stories)
            stories.sort(key=lambda story: story.published, reverse=True)
            stories = dedupe(stories, threshold)[:limit]
            for story in stories:
                self._apply_summary(story)
            sections[config[CONF_SECTION_ID]] = Section(
                id=config[CONF_SECTION_ID],
                name=config[CONF_SECTION_NAME],
                colour=config.get(CONF_COLOUR, DEFAULT_COLOUR),
                stories=stories,
            )
        return BrieflyData(sections=sections, last_updated=now, errors=errors), candidates

    def _apply_summary(self, story: Story) -> None:
        """Set the story's summary fields from the cache."""
        story.summary, story.key_facts = [], []
        if not self.summaries_enabled:
            story.summary_status = STATUS_OFF
            return
        record = self.cache.get_summary(story.id) or {}
        status = record.get("status")
        if status == STATUS_DONE:
            story.summary = list(record.get("summary", []))
            story.key_facts = list(record.get("key_facts", []))
            story.summary_status = STATUS_DONE
        elif status == STATUS_FEED_ONLY or self.http.site_blocked(story.link):
            story.summary_status = STATUS_FEED_ONLY
        else:
            story.summary_status = STATUS_PENDING

    def refresh_statuses(self, data: BrieflyData | None = None) -> None:
        """Re-apply cached summaries to the stories and notify listeners.

        A summary pass started during a refresh may finish before the
        coordinator has stored that refresh's data, so it passes its own data.
        """
        data = data or self.data
        if data is None:
            return
        for _section, story in data.all_stories():
            self._apply_summary(story)
        if self.data is not None and self.data.sections is data.sections:
            self.async_set_updated_data(
                BrieflyData(
                    sections=data.sections,
                    last_updated=data.last_updated,
                    errors=data.errors,
                )
            )

    # Summaries --------------------------------------------------------------
    def pending_in_priority_order(self, data: BrieflyData | None = None) -> list[Story]:
        """Return pending stories, section leads first, then by rank."""
        data = data or self.data
        if data is None:
            return []
        columns = [section.stories for section in data.sections.values()]
        ordered: list[Story] = []
        seen: set[str] = set()
        for rank in range(max((len(c) for c in columns), default=0)):
            for column in columns:
                if rank < len(column):
                    story = column[rank]
                    if story.summary_status == STATUS_PENDING and story.id not in seen:
                        seen.add(story.id)
                        ordered.append(story)
        return ordered

    async def async_summarise_pending(self, data: BrieflyData | None = None) -> int:
        """Summarise up to the per-refresh cap of pending stories."""
        if self._summary_lock.locked():
            return 0
        async with self._summary_lock:
            cap = int(self.settings[CONF_SUMMARIES_PER_REFRESH])
            done = 0
            for story in self.pending_in_priority_order(data)[:cap]:
                if await self.async_summarise_story(story) == STATUS_DONE:
                    done += 1
            self.cache.schedule_save()
            self.refresh_statuses(data)
            return done

    async def async_summarise_story(self, story: Story) -> str:
        """Summarise one story and cache the outcome; return its new status."""
        if self.summariser is None:
            return STATUS_OFF
        result = await self.http.fetch_article(story.link)
        if result.status != ARTICLE_OK:
            if result.status in ("blocked", "disallowed"):
                self.cache.set_feed_only(story.id, result.status)
                return STATUS_FEED_ONLY
            return self._failed(story, result.error)
        text = await self.hass.async_add_executor_job(
            extract_article_text, result.content.decode("utf-8", errors="ignore")
        )
        if len(text) < MIN_ARTICLE_CHARS:
            self.cache.set_feed_only(story.id, "no_text")
            return STATUS_FEED_ONLY
        try:
            summary = await self.summariser.async_summarise(story.title, text)
        except OllamaError as err:
            return self._failed(story, str(err))
        if not numbers_supported(summary, f"{story.title}\n{text}"):
            _LOGGER.info("Rejected summary of %s: a number was not in the article", story.id)
            self.cache.set_feed_only(story.id, "unverified")
            return STATUS_FEED_ONLY
        self.cache.set_done(story.id, summary.paragraphs, summary.key_facts)
        return STATUS_DONE

    def _failed(self, story: Story, error: str) -> str:
        attempts = self.cache.add_attempt(story.id)
        _LOGGER.debug("Summary attempt %s for %s failed: %s", attempts, story.id, error)
        if attempts >= MAX_SUMMARY_ATTEMPTS:
            self.cache.set_feed_only(story.id, "gave_up")
            return STATUS_FEED_ONLY
        return STATUS_PENDING


def _copy(story: Story) -> Story:
    """Return a fresh copy so merges never leak between refreshes or sections."""
    return Story(
        id=story.id,
        title=story.title,
        description=story.description,
        source=story.source,
        link=story.link,
        published=story.published,
        image_small=story.image_small,
        image_large=story.image_large,
    )
