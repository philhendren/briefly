"""Preset news feeds.

Every preset was checked on 2026-11-04: the feed is public, the publisher's
robots.txt allows the article path for an honest automated reader, and an
article request with Briefly's user agent returns 200. Publishers that refuse
automated article fetching (Sky News returned 403, The Telegraph 402) are
deliberately left out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class PresetFeed:
    """A known, fetch-friendly news feed."""

    key: str
    source: str
    topic: str
    url: str

    @property
    def label(self) -> str:
        """Return the label shown in the configuration UI."""
        return f"{self.source} · {self.topic}"


_BBC = "BBC News"
_BBC_SPORT = "BBC Sport"
_GUARDIAN = "The Guardian"
_STANDARD = "The Standard"
_ALJAZEERA = "Al Jazeera"
_NPR = "NPR"
_CONVERSATION = "The Conversation"
_CITYAM = "City AM"

PRESET_FEEDS: Final[dict[str, PresetFeed]] = {
    feed.key: feed
    for feed in (
        PresetFeed("bbc_uk", _BBC, "UK", "https://feeds.bbci.co.uk/news/uk/rss.xml"),
        PresetFeed(
            "bbc_politics",
            _BBC,
            "Politics",
            "https://feeds.bbci.co.uk/news/politics/rss.xml",
        ),
        PresetFeed("bbc_world", _BBC, "World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        PresetFeed(
            "bbc_business",
            _BBC,
            "Business",
            "https://feeds.bbci.co.uk/news/business/rss.xml",
        ),
        PresetFeed(
            "bbc_technology",
            _BBC,
            "Technology",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
        ),
        PresetFeed(
            "bbc_science",
            _BBC,
            "Science & Environment",
            "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        ),
        PresetFeed("bbc_health", _BBC, "Health", "https://feeds.bbci.co.uk/news/health/rss.xml"),
        PresetFeed("bbc_sport", _BBC_SPORT, "Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
        PresetFeed("guardian_uk", _GUARDIAN, "UK", "https://www.theguardian.com/uk/rss"),
        PresetFeed(
            "guardian_politics",
            _GUARDIAN,
            "Politics",
            "https://www.theguardian.com/politics/rss",
        ),
        PresetFeed("guardian_world", _GUARDIAN, "World", "https://www.theguardian.com/world/rss"),
        PresetFeed(
            "guardian_business",
            _GUARDIAN,
            "Business",
            "https://www.theguardian.com/uk/business/rss",
        ),
        PresetFeed(
            "guardian_technology",
            _GUARDIAN,
            "Technology",
            "https://www.theguardian.com/uk/technology/rss",
        ),
        PresetFeed(
            "guardian_environment",
            _GUARDIAN,
            "Environment",
            "https://www.theguardian.com/uk/environment/rss",
        ),
        PresetFeed(
            "guardian_sport",
            _GUARDIAN,
            "Sport",
            "https://www.theguardian.com/uk/sport/rss",
        ),
        PresetFeed("standard_uk", _STANDARD, "UK", "https://www.standard.co.uk/news/uk/rss"),
        PresetFeed(
            "standard_politics",
            _STANDARD,
            "Politics",
            "https://www.standard.co.uk/news/politics/rss",
        ),
        PresetFeed("standard_sport", _STANDARD, "Sport", "https://www.standard.co.uk/sport/rss"),
        PresetFeed(
            "aljazeera_all",
            _ALJAZEERA,
            "All news",
            "https://www.aljazeera.com/xml/rss/all.xml",
        ),
        PresetFeed("npr_news", _NPR, "News", "https://feeds.npr.org/1001/rss.xml"),
        PresetFeed("npr_world", _NPR, "World", "https://feeds.npr.org/1004/rss.xml"),
        PresetFeed(
            "conversation_uk",
            _CONVERSATION,
            "UK",
            "https://theconversation.com/uk/articles.atom",
        ),
        PresetFeed("cityam_business", _CITYAM, "Business", "https://www.cityam.com/feed/"),
    )
}

# Suggested sections offered, in order, while setting up a new desk.
SUGGESTED_SECTIONS: Final[list[tuple[str, str, list[str]]]] = [
    ("UK", "#1e88e5", ["bbc_uk", "guardian_uk"]),
    ("Politics", "#8e24aa", ["bbc_politics", "guardian_politics"]),
    ("Sport", "#43a047", ["bbc_sport", "guardian_sport"]),
]
