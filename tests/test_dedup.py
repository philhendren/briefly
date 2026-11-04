"""Duplicate removal."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.briefly.dedup import dedupe, similarity, title_tokens
from custom_components.briefly.models import Story

NOW = datetime(2026, 11, 4, 8, tzinfo=UTC)


def story(sid: str, title: str, source: str = "BBC News", image: str | None = None) -> Story:
    return Story(
        id=sid,
        title=title,
        description="",
        source=source,
        link=f"https://x.example/{sid}",
        published=NOW,
        image_small=image,
        image_large=image,
    )


def test_title_tokens_strip_suffix_stopwords_and_plurals() -> None:
    tokens = title_tokens("Council approves 250 new homes on edge of town | Jane Writer")
    assert tokens == frozenset({"council", "approve", "250", "home", "edge", "town"})
    assert "glass" in title_tokens("Glass prices rise")


def test_similarity_handles_empty() -> None:
    assert similarity(frozenset(), frozenset({"a"})) == 0.0
    assert similarity(frozenset({"a", "b"}), frozenset({"a"})) == 0.5


def test_dedupe_folds_similar_titles_and_borrows_image() -> None:
    first = story("1", "Council approves 250 new homes on town edge")
    second = story("2", "Council approves 250 new homes on edge of town", "The Guardian", "img")
    third = story("3", "Museum reopens after restoration", "The Guardian")
    kept = dedupe([first, second, third], 0.5)
    assert kept == [first, third]
    assert first.also_reported_by == ["The Guardian"]
    assert first.image_small == "img"


def test_dedupe_identical_ids_always_fold() -> None:
    first = story("1", "Same story", image="keep")
    copy = story("1", "Same story", "BBC News", "other")
    other_outlet = story("1", "Same story", "The Guardian")
    assert dedupe([first, copy, other_outlet], None) == [first]
    assert first.also_reported_by == ["The Guardian"]
    assert first.image_small == "keep"


def test_dedupe_off_keeps_similar_titles() -> None:
    first = story("1", "Council approves 250 new homes on town edge")
    second = story("2", "Council approves 250 new homes on edge of town", "The Guardian")
    assert dedupe([first, second], None) == [first, second]


def test_dedupe_later_duplicate_of_merged_id() -> None:
    first = story("1", "Council approves 250 new homes on town edge")
    second = story("2", "Council approves 250 new homes on edge of town", "The Guardian")
    again = story("2", "Council approves 250 new homes on edge of town", "The Standard")
    assert dedupe([first, second, again], 0.5) == [first]
    assert first.also_reported_by == ["The Guardian", "The Standard"]
