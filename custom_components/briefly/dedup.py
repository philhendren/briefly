"""Remove the same story when several outlets carry it."""

from __future__ import annotations

import re

from .models import Story

_STOPWORDS = frozenset(
    """a an and are as at be by for from has have he her his in is it
    its of on or over says said she that the their they this to was were will with
    after into up out new more than not but who what how why""".split()  # noqa: SIM905
)
# Guardian and others append " | Author" or " - Outlet" to titles.
_SUFFIX = re.compile(r"\s+[|–—-]\s+[^|–—-]{1,40}$")
_WORD = re.compile(r"[a-z0-9£$€%]+")


def title_tokens(title: str) -> frozenset[str]:
    """Return the significant, lightly stemmed words of a title."""
    text = _SUFFIX.sub("", title).lower().replace("’", "'").replace("'s", "")
    tokens = set()
    for word in _WORD.findall(text):
        if word in _STOPWORDS:
            continue
        plural = len(word) > 3 and word.endswith("s") and not word.endswith("ss")
        tokens.add(word[:-1] if plural else word)
    return frozenset(tokens)


def similarity(first: frozenset[str], second: frozenset[str]) -> float:
    """Return the Jaccard similarity of two token sets."""
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def dedupe(stories: list[Story], threshold: float | None) -> list[Story]:
    """Return stories with duplicates folded into the first (preferred) copy.

    Stories are expected best-first. Identical ids are always folded; similar
    titles are folded when `threshold` is set. The kept story records the other
    outlets in `also_reported_by` and borrows an image if it has none.
    """
    kept: list[tuple[Story, frozenset[str]]] = []
    by_id: dict[str, Story] = {}
    for story in stories:
        if story.id in by_id:
            _merge(by_id[story.id], story)
            continue
        tokens = title_tokens(story.title)
        match = None
        if threshold is not None:
            match = next(
                (
                    existing
                    for existing, existing_tokens in kept
                    if similarity(tokens, existing_tokens) >= threshold
                ),
                None,
            )
        if match is not None:
            _merge(match, story)
            by_id[story.id] = match
            continue
        kept.append((story, tokens))
        by_id[story.id] = story
    return [story for story, _tokens in kept]


def _merge(keep: Story, duplicate: Story) -> None:
    if duplicate.source != keep.source and duplicate.source not in keep.also_reported_by:
        keep.also_reported_by.append(duplicate.source)
    if keep.image_small is None and duplicate.image_small is not None:
        keep.image_small = duplicate.image_small
        keep.image_large = duplicate.image_large
