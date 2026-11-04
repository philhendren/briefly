"""Feed parsing: RSS/Atom bytes in, stories out.

Everything here is pure and synchronous so it can run in the executor and be
unit tested without Home Assistant.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

from .models import Story

DESCRIPTION_LIMIT = 400
SMALL_TARGET_WIDTH = 320
UNKNOWN_WIDTH = 1000
_TRACKING_PREFIXES = ("utm_", "at_")
_BBC_ICHEF = re.compile(r"(ichef\.bbci\.co\.uk/(?:ace|news)/(?:standard|ws)/)(\d+)(/)")
_IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp|avif)$", re.IGNORECASE)
_TRAILERS = re.compile(r"\s*(continue reading\.*|read more\.*)\s*$", re.IGNORECASE)


class FeedError(Exception):
    """Raised when content is not a usable RSS or Atom feed."""


@dataclass(slots=True)
class ParsedFeed:
    """A parsed feed."""

    title: str
    stories: list[Story]


class _TextExtractor(HTMLParser):
    """Collect visible text from an HTML fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("p", "br", "div", "li"):
            self.parts.append(" ")


def html_to_text(fragment: str) -> str:
    """Return plain text from an HTML fragment, whitespace collapsed."""
    parser = _TextExtractor()
    parser.feed(fragment)
    parser.close()
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def truncate(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """Truncate text at a word boundary, adding an ellipsis when cut."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.-")
    return f"{cut}…"


def canonical_link(link: str) -> str:
    """Return the link without tracking parameters or fragment."""
    parts = urlsplit(link.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def story_id(link: str) -> str:
    """Return a short stable id for a story link."""
    return hashlib.sha1(canonical_link(link).encode(), usedforsecurity=False).hexdigest()[:10]


def _width(value: Any) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return UNKNOWN_WIDTH


def image_candidates(entry: Any) -> list[tuple[int, str]]:
    """Return (width, url) for every image an entry offers."""
    found: list[tuple[int, str]] = []
    for thumb in entry.get("media_thumbnail") or []:
        if url := thumb.get("url"):
            found.append((_width(thumb.get("width")), url))
    for media in entry.get("media_content") or []:
        url = media.get("url")
        kind = (media.get("type") or "").lower()
        medium = (media.get("medium") or "").lower()
        # The Guardian gives only url and width, so an untyped item counts as an
        # image when it has a width or an image file extension.
        untyped_image = (
            not kind
            and not medium
            and ("width" in media or _IMAGE_EXT.search(urlsplit(url or "").path))
        )
        if url and (kind.startswith("image/") or medium == "image" or untyped_image):
            found.append((_width(media.get("width")), url))
    for enclosure in entry.get("enclosures") or []:
        url = enclosure.get("href") or enclosure.get("url")
        if url and (enclosure.get("type") or "").lower().startswith("image/"):
            found.append((UNKNOWN_WIDTH, url))
    return found


def _resize_bbc(url: str, width: int) -> str:
    return _BBC_ICHEF.sub(rf"\g<1>{width}\g<3>", url)


def pick_images(candidates: list[tuple[int, str]]) -> tuple[str | None, str | None]:
    """Choose a small (list thumbnail) and a large (lead / pop-up) image."""
    if not candidates:
        return None, None
    by_width = sorted(candidates, key=lambda item: item[0])
    small = next((url for width, url in by_width if width >= SMALL_TARGET_WIDTH), by_width[-1][1])
    large = by_width[-1][1]
    # BBC only publishes 240px thumbnails, but its image server takes the width
    # from the path, so ask it for sensible sizes instead.
    if _BBC_ICHEF.search(small):
        small = _resize_bbc(small, 480)
    if _BBC_ICHEF.search(large):
        large = _resize_bbc(large, 976)
    return small, large


def _published(entry: Any, fallback: datetime) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        if parsed := entry.get(key):
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
    return fallback


def clean_title(title: str) -> str:
    """Return a tidy title."""
    return re.sub(r"\s+", " ", html_to_text(title)).strip()


def parse_feed(
    content: bytes, source: str | None = None, now: datetime | None = None
) -> ParsedFeed:
    """Parse RSS or Atom bytes into stories.

    `source` overrides the publisher name; otherwise the feed's own title is used.
    """
    now = now or datetime.now(UTC)
    parsed = feedparser.parse(content)
    if not parsed.get("version") and not parsed.entries:
        raise FeedError("Not an RSS or Atom feed")
    feed_title = clean_title(parsed.feed.get("title", "")) or "News"
    source_name = source or feed_title
    stories: list[Story] = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = clean_title(entry.get("title", ""))
        if not link or not title:
            continue
        raw = entry.get("summary") or entry.get("description") or ""
        description = truncate(_TRAILERS.sub("", html_to_text(raw)))
        small, large = pick_images(image_candidates(entry))
        stories.append(
            Story(
                id=story_id(link),
                title=title,
                description=description,
                source=source_name,
                link=canonical_link(link),
                published=_published(entry, now),
                image_small=small,
                image_large=large,
            )
        )
    return ParsedFeed(title=feed_title, stories=stories)
