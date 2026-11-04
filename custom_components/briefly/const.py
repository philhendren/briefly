"""Constants for the Briefly integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "briefly"
VERSION: Final = "0.1.0"
PROJECT_URL: Final = "https://github.com/philhendren/briefly"

# Honest user agent: never imitate a browser.
ROBOTS_AGENT: Final = "HomeAssistant-Briefly"
USER_AGENT: Final = f"{ROBOTS_AGENT}/{VERSION} (+{PROJECT_URL})"

# Config entry data / options keys
CONF_NAME: Final = "name"
CONF_SECTIONS: Final = "sections"
CONF_SECTION_ID: Final = "id"
CONF_SECTION_NAME: Final = "section_name"
CONF_COLOUR: Final = "colour"
CONF_FEEDS: Final = "feeds"
CONF_CUSTOM_FEEDS: Final = "custom_feeds"
CONF_ADD_ANOTHER: Final = "add_another"

CONF_REFRESH_MINUTES: Final = "refresh_minutes"
CONF_STORIES_PER_SECTION: Final = "stories_per_section"
CONF_MAX_AGE_HOURS: Final = "max_age_hours"
CONF_DEDUP: Final = "dedup"
CONF_SUMMARIES_PER_REFRESH: Final = "summaries_per_refresh"

CONF_SUMMARY_MODE: Final = "summary_mode"
CONF_OLLAMA_URL: Final = "ollama_url"
CONF_MODEL: Final = "model"
CONF_SUMMARY_LENGTH: Final = "summary_length"

CONF_ALEXA_ENABLED: Final = "alexa_enabled"
CONF_ALEXA_TARGETS: Final = "alexa_targets"

# Summary modes
SUMMARY_OFF: Final = "off"
SUMMARY_OLLAMA: Final = "ollama"
SUMMARY_MODES: Final = [SUMMARY_OFF, SUMMARY_OLLAMA]

# Summary lengths
LENGTH_HEADLINE: Final = "headline"
LENGTH_SHORT: Final = "short"
LENGTH_MEDIUM: Final = "medium"
SUMMARY_LENGTHS: Final = [LENGTH_HEADLINE, LENGTH_SHORT, LENGTH_MEDIUM]

# Duplicate thresholds (Jaccard similarity of title words)
DEDUP_OFF: Final = "off"
DEDUP_LOOSE: Final = "loose"
DEDUP_NORMAL: Final = "normal"
DEDUP_STRICT: Final = "strict"
DEDUP_LEVELS: Final = [DEDUP_OFF, DEDUP_LOOSE, DEDUP_NORMAL, DEDUP_STRICT]
DEDUP_THRESHOLDS: Final[dict[str, float | None]] = {
    DEDUP_OFF: None,
    DEDUP_LOOSE: 0.35,
    DEDUP_NORMAL: 0.5,
    DEDUP_STRICT: 0.7,
}

DEFAULT_NAME: Final = "News"
DEFAULT_OLLAMA_URL: Final = "http://localhost:11434"
DEFAULT_REFRESH_MINUTES: Final = 30
DEFAULT_STORIES_PER_SECTION: Final = 10
DEFAULT_MAX_AGE_HOURS: Final = 48
DEFAULT_DEDUP: Final = DEDUP_NORMAL
DEFAULT_SUMMARIES_PER_REFRESH: Final = 8
DEFAULT_SUMMARY_LENGTH: Final = LENGTH_SHORT
DEFAULT_COLOUR: Final = "#1e88e5"

REFRESH_RANGE: Final = (10, 240)
STORIES_RANGE: Final = (3, 25)
MAX_AGE_RANGE: Final = (6, 168)
SUMMARIES_RANGE: Final = (1, 30)

DEFAULT_SETTINGS: Final = {
    CONF_REFRESH_MINUTES: DEFAULT_REFRESH_MINUTES,
    CONF_STORIES_PER_SECTION: DEFAULT_STORIES_PER_SECTION,
    CONF_MAX_AGE_HOURS: DEFAULT_MAX_AGE_HOURS,
    CONF_DEDUP: DEFAULT_DEDUP,
    CONF_SUMMARIES_PER_REFRESH: DEFAULT_SUMMARIES_PER_REFRESH,
}

# Summary status values exposed on every story
STATUS_DONE: Final = "done"
STATUS_PENDING: Final = "pending"
STATUS_OFF: Final = "off"
STATUS_FEED_ONLY: Final = "feed_only"

# Publisher etiquette
BLOCK_STATUSES: Final = frozenset({401, 402, 403, 429})
BLOCK_DURATION: Final = timedelta(days=7)
ROBOTS_TTL: Final = timedelta(hours=24)
MAX_ARTICLE_CHARS: Final = 7000
MIN_ARTICLE_CHARS: Final = 200
MAX_SUMMARY_ATTEMPTS: Final = 3
MAX_DOWNLOAD_BYTES: Final = 3 * 1024 * 1024
HTTP_TIMEOUT: Final = 20
OLLAMA_TIMEOUT: Final = 180

# Image proxy
IMAGE_URL: Final = "/api/briefly/image/{story_id}"
IMAGE_CACHE_DIR: Final = ".cache/briefly_images"
IMAGE_CACHE_TTL: Final = timedelta(hours=48)

# Cache retention
CACHE_RETENTION: Final = timedelta(days=7)
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = "briefly_cache"

# Alexa Media Player (separate custom integration from HACS)
ALEXA_MEDIA_DOMAIN: Final = "alexa_media"
ALEXA_NOTIFY_SERVICE: Final = "alexa_media"

# Services
SERVICE_REFRESH: Final = "refresh"
SERVICE_GET_STORIES: Final = "get_stories"
SERVICE_SUMMARISE: Final = "summarise"
SERVICE_SPEAK_HEADLINES: Final = "speak_headlines"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_SECTION: Final = "section"
ATTR_COUNT: Final = "count"
ATTR_STORY_ID: Final = "story_id"
ATTR_TARGETS: Final = "targets"

EVENT_NEW_STORY: Final = "new_story"
