"""Data models for Briefly."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import IMAGE_URL, STATUS_PENDING


@dataclass(slots=True)
class Story:
    """One news story taken from a feed."""

    id: str
    title: str
    description: str
    source: str
    link: str
    published: datetime
    image_small: str | None = None
    image_large: str | None = None
    summary: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    summary_status: str = STATUS_PENDING
    also_reported_by: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return the story as exposed in sensor attributes and services."""
        base = IMAGE_URL.format(story_id=self.id)
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "link": self.link,
            "image": f"{base}?size=small" if self.image_small else None,
            "image_large": f"{base}?size=large" if self.image_large else None,
            "published": self.published.isoformat(),
            "summary": list(self.summary),
            "key_facts": list(self.key_facts),
            "summary_status": self.summary_status,
            "also_reported_by": list(self.also_reported_by),
        }


@dataclass(slots=True)
class Section:
    """A named group of feeds and its current stories."""

    id: str
    name: str
    colour: str
    stories: list[Story] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        """Return the distinct sources represented in this section."""
        seen: dict[str, None] = {}
        for story in self.stories:
            seen.setdefault(story.source, None)
            for other in story.also_reported_by:
                seen.setdefault(other, None)
        return list(seen)


@dataclass(slots=True)
class BrieflyData:
    """Everything one refresh produced."""

    sections: dict[str, Section]
    last_updated: datetime
    new_stories: list[tuple[str, Story]] = field(default_factory=list)
    errors: int = 0

    def all_stories(self) -> list[tuple[Section, Story]]:
        """Return every story with its section, section by section."""
        return [(section, story) for section in self.sections.values() for story in section.stories]

    def find_story(self, story_id: str) -> Story | None:
        """Return the story with this id, if it is currently listed."""
        for _section, story in self.all_stories():
            if story.id == story_id:
                return story
        return None

    def count_status(self, status: str) -> int:
        """Return how many unique listed stories have this summary status."""
        return len({story.id for _s, story in self.all_stories() if story.summary_status == status})
