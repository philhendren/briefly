"""BDD: choosing news sources."""

from __future__ import annotations

from typing import Any

from pytest_bdd import parsers, scenarios, then, when

from homeassistant.core import HomeAssistant

from .conftest import UK_SECTION, configure, settle, start_flow

scenarios("news_sources.feature")


def feed_selector(ctx: dict[str, Any]):
    schema = ctx["result"]["data_schema"].schema
    return schema[next(key for key in schema if key == "feeds")]


def labels(ctx: dict[str, Any]) -> list[str]:
    return [option["label"] for option in feed_selector(ctx).config["options"]]


@then(parsers.parse('the section form offers the source "{label}"'))
def offers(ctx: dict[str, Any], label: str) -> None:
    assert ctx["result"]["step_id"] == "section"
    assert label in labels(ctx)


@then(parsers.parse('the section form offers no "{publisher}" source'))
def offers_none(ctx: dict[str, Any], publisher: str) -> None:
    assert not [label for label in labels(ctx) if publisher in label]


@then("the sources are shown as a list, not a drop-down")
def shown_as_list(ctx: dict[str, Any]) -> None:
    assert feed_selector(ctx).config["mode"] == "list"


@when(parsers.parse('I set up a news desk called "{name}" with a section "{section}" using "{keys}"'))
def set_up_desk(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, name: str, section: str, keys: str) -> None:
    start_flow(hass, ctx, aioclient_mock, name)
    feeds = [key.strip() for key in keys.split(",")]
    configure(hass, ctx, {**UK_SECTION, "section_name": section, "feeds": feeds})
    configure(hass, ctx, {"summary_mode": "off"})
    result = configure(hass, ctx, {"alexa_enabled": False})
    assert result["type"] == "create_entry"
    settle(hass)


@when(parsers.parse('I add a section "{name}" with the custom feed "{url}" that serves a web page'))
def add_bad_feed(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, name: str, url: str) -> None:
    aioclient_mock.get(url, text="<html><body>Hello</body></html>")
    configure(hass, ctx, {**UK_SECTION, "section_name": name, "feeds": [], "custom_feeds": url})


def stories(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    return hass.states.get(entity_id).attributes["stories"]


@then(parsers.parse('"{entity_id}" lists {count:d} stories'))
def lists(hass: HomeAssistant, entity_id: str, count: int) -> None:
    assert hass.states.get(entity_id).state == str(count)
    assert len(stories(hass, entity_id)) == count


@then(parsers.parse('every story in "{entity_id}" comes from "{first}" or "{second}"'))
def sources(hass: HomeAssistant, entity_id: str, first: str, second: str) -> None:
    assert {s["source"] for s in stories(hass, entity_id)} <= {first, second}


@then(parsers.parse('the lead story in "{entity_id}" is "{title}"'))
def lead(hass: HomeAssistant, entity_id: str, title: str) -> None:
    assert stories(hass, entity_id)[0]["title"] == title


@then(parsers.parse('the lead story in "{entity_id}" is also reported by "{source}"'))
def also(hass: HomeAssistant, entity_id: str, source: str) -> None:
    assert source in stories(hass, entity_id)[0]["also_reported_by"]
    titles = [s["title"] for s in stories(hass, entity_id)]
    assert not any(t.endswith("| Jane Writer") for t in titles)
