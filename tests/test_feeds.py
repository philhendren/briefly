"""Feed parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.briefly.feeds import (
    FeedError,
    canonical_link,
    html_to_text,
    image_candidates,
    parse_feed,
    pick_images,
    story_id,
    truncate,
)

from .helpers import Item, atom, bbc_uk_feed, guardian_uk_feed, rss


def test_parse_rss_uses_feed_title_and_cleans_links() -> None:
    parsed = parse_feed(bbc_uk_feed().encode())
    assert parsed.title == "BBC News"
    first = parsed.stories[0]
    assert first.source == "BBC News"
    assert first.link == "https://www.bbc.co.uk/news/articles/homes1"
    assert first.id == story_id("https://www.bbc.co.uk/news/articles/homes1?utm_source=x")
    assert first.image_small.endswith("/480/cpsprodpb/aaa/live/homes.jpg")
    assert first.image_large.endswith("/976/cpsprodpb/aaa/live/homes.jpg")
    assert first.published.tzinfo is not None


def test_parse_rss_source_override_and_html_description() -> None:
    parsed = parse_feed(guardian_uk_feed().encode(), "Guardian")
    homes = parsed.stories[0]
    assert homes.source == "Guardian"
    assert homes.description == "Plans approved after a vote."
    assert homes.image_small == "https://i.guim.co.uk/img/homes-460.jpg"
    assert homes.image_large == "https://i.guim.co.uk/img/homes-460.jpg"
    assert parsed.stories[1].image_small is None


def test_parse_atom() -> None:
    parsed = parse_feed(atom("The Conversation", [Item("Atom story", "https://a.example/1")]).encode())
    assert parsed.title == "The Conversation"
    assert parsed.stories[0].title == "Atom story"


def test_parse_skips_items_without_link_or_title_and_defaults() -> None:
    body = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><title>No link</title></item>"
        "<item><link>https://x.example/no-title</link></item>"
        "<item><title>Undated</title><link>https://x.example/undated</link></item>"
        "</channel></rss>"
    )
    now = datetime(2026, 11, 4, 8, tzinfo=UTC)
    parsed = parse_feed(body.encode(), now=now)
    assert parsed.title == "News"
    assert [s.title for s in parsed.stories] == ["Undated"]
    assert parsed.stories[0].published == now
    assert parsed.stories[0].description == ""


def test_parse_rejects_non_feed() -> None:
    with pytest.raises(FeedError):
        parse_feed(b"<html><body>Not a feed</body></html>")


def test_enclosure_and_unknown_width_images() -> None:
    feed = rss(
        "Example",
        [
            Item("Enclosure", "https://x.example/1", enclosure="https://img.example/e.jpg"),
            Item("Media", "https://x.example/2", media=[("https://img.example/m.jpg", None)]),
        ],
    )
    stories = parse_feed(feed.encode()).stories
    assert stories[0].image_small == "https://img.example/e.jpg"
    assert stories[1].image_large == "https://img.example/m.jpg"


def test_untyped_media_content_counts_as_image() -> None:
    entry = {
        "media_content": [
            {"url": "https://i.guim.co.uk/img/a.jpg?width=460&s=x", "width": "460"},
            {"url": "https://cdn.example/photo.webp"},
            {"url": "https://cdn.example/clip"},
        ]
    }
    assert image_candidates(entry) == [
        (460, "https://i.guim.co.uk/img/a.jpg?width=460&s=x"),
        (1000, "https://cdn.example/photo.webp"),
    ]


def test_image_candidates_ignore_non_images() -> None:
    entry = {
        "media_thumbnail": [{"url": ""}, {"url": "https://t/1.jpg", "width": "120"}],
        "media_content": [{"url": "https://v/1.mp4", "type": "video/mp4"}],
        "enclosures": [{"href": "https://a/1.mp3", "type": "audio/mpeg"}, {"type": "image/png"}],
    }
    assert image_candidates(entry) == [(120, "https://t/1.jpg")]


def test_pick_images() -> None:
    assert pick_images([]) == (None, None)
    small, large = pick_images([(100, "a"), (200, "b")])
    assert small == "b"  # nothing reaches 320px: use the biggest
    assert large == "b"
    small, large = pick_images([(100, "a"), (400, "b"), (900, "c")])
    assert (small, large) == ("b", "c")


def test_text_helpers() -> None:
    assert html_to_text("<p>One</p><p>Two &amp; three</p>") == "One Two & three"
    assert truncate("short") == "short"
    long = "word " * 200
    cut = truncate(long, 50)
    assert cut.endswith("…") and len(cut) <= 51
    assert canonical_link("https://x.example/a?id=3&utm_medium=rss#top") == "https://x.example/a?id=3"
