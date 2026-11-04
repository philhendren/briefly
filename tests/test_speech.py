"""Building the words Alexa says."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.briefly.models import Story
from custom_components.briefly.speech import build_headline_script, speakable


def story(title: str, source: str = "BBC News") -> Story:
    return Story("1", title, "", source, "https://x", datetime(2026, 11, 4, tzinfo=UTC))


def test_script() -> None:
    text = build_headline_script(
        "Kiosk news", [story("Trains & buses <b>cut</b>."), story("Rain due", "The Guardian")]
    )
    assert text == (
        "Here are the top 2 headlines from Kiosk news. From BBC News: Trains and buses bcut/b. "
        "From The Guardian: Rain due."
    )


def test_empty_script() -> None:
    assert (
        build_headline_script("Kiosk news", [], "Sport")
        == "There are no headlines from Sport news right now."
    )


def test_speakable() -> None:
    assert speakable("  A [b]  {c}\\ ") == "A b c"
