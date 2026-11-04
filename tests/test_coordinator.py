"""Refreshes, events and Ollama summaries (all HTTP mocked)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.briefly.const import CONF_SECTIONS
from custom_components.briefly.coordinator import section_feeds

from .helpers import (
    BBC_UK,
    CONNECTION_ERROR,
    CUSTOM_FEED,
    GUARDIAN_UK,
    HTML,
    XML,
    FakeOllama,
    Item,
    bbc_uk_feed,
    make_entry,
    register_feeds,
    rss,
    sections_uk_sport,
    setup_entry,
)


def stories(hass: HomeAssistant, section: str = "uk") -> list[dict]:
    return hass.states.get(f"sensor.kiosk_news_{section}").attributes["stories"]


def by_title(hass: HomeAssistant, start: str) -> dict:
    return next(s for s in stories(hass) if s["title"].startswith(start))


async def refresh(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_summaries_written_and_cached(hass: HomeAssistant, feeds, ollama: FakeOllama) -> None:
    entry = make_entry(summaries=True)
    await setup_entry(hass, entry)
    homes = by_title(hass, "Council approves")
    assert homes["summary_status"] == "done"
    assert homes["summary"][0].startswith("The council has approved plans for 250 new homes")
    assert homes["key_facts"]
    last = hass.states.get("sensor.kiosk_news_last_updated").attributes
    assert last["summarised"] == 4
    assert last["pending"] == 0
    assert last["errors"] == 0
    # Leads first: the first two requests are the UK and Sport section leads.
    heads = [
        r["messages"][1]["content"].split("Headline: ")[1].split("\n")[0] for r in ollama.requests
    ]
    assert heads[0].startswith("Council approves")
    assert heads[1].startswith("Local club")

    # Each story is summarised once, even across refreshes.
    count = len(ollama.requests)
    await refresh(hass)
    assert len(ollama.requests) == count
    assert by_title(hass, "Council approves")["summary_status"] == "done"


async def test_summary_with_invented_number_is_rejected(
    hass: HomeAssistant, feeds, ollama: FakeOllama
) -> None:
    ollama.default = {"summary": ["The council approved 999 homes."], "key_facts": []}
    await setup_entry(hass, make_entry(summaries=True))
    homes = by_title(hass, "Council approves")
    assert homes["summary_status"] == "feed_only"
    assert homes["summary"] == []
    assert homes["description"] == "Plans include a school and a health centre."


async def test_ollama_down_retries_three_times(
    hass: HomeAssistant, feeds, ollama: FakeOllama
) -> None:
    ollama.replies = [CONNECTION_ERROR] * 100
    await setup_entry(hass, make_entry(summaries=True))
    assert by_title(hass, "Council approves")["summary_status"] == "pending"
    assert hass.states.get("sensor.kiosk_news_last_updated").attributes["pending"] == 4
    await refresh(hass)
    assert by_title(hass, "Council approves")["summary_status"] == "pending"
    await refresh(hass)
    assert by_title(hass, "Council approves")["summary_status"] == "feed_only"
    calls = len(ollama.requests)
    await refresh(hass)
    assert len(ollama.requests) == calls  # gave up


async def test_publisher_refusal_marks_site_feed_only(
    hass: HomeAssistant, aioclient_mock, ollama: FakeOllama
) -> None:
    aioclient_mock.get("https://www.bbc.co.uk/news/articles/homes1", status=403)
    register_feeds(aioclient_mock)
    await setup_entry(hass, make_entry(summaries=True, summaries_per_refresh=1))
    assert by_title(hass, "Council approves")["summary_status"] == "feed_only"
    # The other BBC story is now feed-only too, without any request.
    assert by_title(hass, "Weekend rail")["summary_status"] == "feed_only"
    assert by_title(hass, "Museum reopens")["summary_status"] == "pending"
    assert not any("rail1" in str(c[1]) for c in aioclient_mock.mock_calls)


async def test_robots_disallow_and_thin_article(
    hass: HomeAssistant, aioclient_mock, ollama: FakeOllama
) -> None:
    aioclient_mock.get(
        "https://www.bbc.co.uk/robots.txt", text="User-agent: *\nDisallow: /news/articles/homes1\n"
    )
    aioclient_mock.get(
        "https://www.bbc.co.uk/news/articles/rail1", text="<p>Video only.</p>", headers=HTML
    )
    aioclient_mock.get("https://sport.example.com/bbc/cup", exc=CONNECTION_ERROR)
    register_feeds(aioclient_mock)
    await setup_entry(hass, make_entry(summaries=True))
    assert by_title(hass, "Council approves")["summary_status"] == "feed_only"
    assert by_title(hass, "Weekend rail")["summary_status"] == "feed_only"
    assert stories(hass, "sport")[0]["summary_status"] == "pending"


async def test_new_story_event(hass: HomeAssistant, aioclient_mock) -> None:
    register_feeds(aioclient_mock)
    await setup_entry(hass, make_entry())
    event = hass.states.get("event.kiosk_news_new_story")
    assert event.state == "unknown"  # nothing is "new" on the very first refresh

    aioclient_mock.clear_requests()
    fresh = Item(
        "Breaking: bridge reopens to traffic",
        "https://www.bbc.co.uk/news/articles/bridge1",
        age_minutes=1,
    )
    aioclient_mock.get(BBC_UK, text=rss("BBC News", [fresh]), headers=XML)
    register_feeds(aioclient_mock)
    await refresh(hass)
    event = hass.states.get("event.kiosk_news_new_story")
    assert event.attributes["event_type"] == "new_story"
    assert event.attributes["title"] == "Breaking: bridge reopens to traffic"
    assert event.attributes["section"] == "UK"
    assert event.attributes["source"] == "BBC News"


async def test_all_feeds_failing_retries_setup(hass: HomeAssistant, aioclient_mock) -> None:
    for url in (BBC_UK, GUARDIAN_UK):
        aioclient_mock.get(url, status=500)
    entry = make_entry(sections=sections_uk_sport()[:1])
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_partial_failure_and_stale_cache(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(CUSTOM_FEED, text="<html>not a feed</html>")
    register_feeds(aioclient_mock)
    sections = sections_uk_sport(custom=[CUSTOM_FEED])
    await setup_entry(hass, make_entry(sections=sections))
    assert hass.states.get("sensor.kiosk_news_last_updated").attributes["errors"] == 1

    # BBC now fails and Guardian is unchanged: the last good stories stay listed.
    aioclient_mock.clear_requests()
    aioclient_mock.get(BBC_UK, status=502)
    aioclient_mock.get(GUARDIAN_UK, status=304)
    aioclient_mock.get(CUSTOM_FEED, text="<html>not a feed</html>")
    register_feeds(aioclient_mock)
    await refresh(hass)
    assert hass.states.get("sensor.kiosk_news_uk").state == "3"
    assert hass.states.get("sensor.kiosk_news_last_updated").attributes["errors"] == 2


async def test_not_modified_without_cache_counts_as_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(GUARDIAN_UK, status=304)
    register_feeds(aioclient_mock)
    await setup_entry(hass, make_entry())
    assert hass.states.get("sensor.kiosk_news_last_updated").attributes["errors"] == 1


async def test_removed_section_sensor_is_cleaned_up(hass: HomeAssistant, feeds) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    registry = er.async_get(hass)
    assert registry.async_get("sensor.kiosk_news_sport")
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_SECTIONS: sections_uk_sport()[:1]}
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get("sensor.kiosk_news_sport") is None


async def test_unload_and_remove(hass: HomeAssistant, feeds, hass_storage) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    key = f"briefly_cache.{entry.entry_id}"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass_storage[key]["data"]["seen"]
    await hass.config_entries.async_remove(entry.entry_id)
    assert key not in hass_storage


async def test_coordinator_edge_cases(hass: HomeAssistant, feeds, ollama: FakeOllama) -> None:
    entry = make_entry(summaries=True)
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    # A running summary pass is not started twice.
    async with coordinator._summary_lock:
        assert await coordinator.async_summarise_pending() == 0
    data = coordinator.data
    coordinator.data = None
    assert coordinator.pending_in_priority_order() == []
    coordinator.refresh_statuses()
    coordinator.data = data
    story = data.find_story(stories(hass)[0]["id"])
    coordinator.summariser = None
    assert await coordinator.async_summarise_story(story) == "off"


async def test_button_refreshes(hass: HomeAssistant, feeds) -> None:
    await setup_entry(hass, make_entry())
    feeds.mock_calls.clear()
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.kiosk_news_refresh"}, blocking=True
    )
    await hass.async_block_till_done()
    assert any(str(c[1]) == BBC_UK for c in feeds.mock_calls)


def test_section_feeds_ignores_unknown_presets() -> None:
    refs = section_feeds({"feeds": ["bbc_uk", "gone"], "custom_feeds": [CUSTOM_FEED]})
    assert [r.url for r in refs] == [BBC_UK, CUSTOM_FEED]
    assert refs[0].source == "BBC News"
    assert refs[1].source is None
    assert bbc_uk_feed()


async def test_priority_order_skips_done_and_shared_stories(
    hass: HomeAssistant, feeds, ollama: FakeOllama
) -> None:
    from custom_components.briefly.models import BrieflyData, Section

    entry = make_entry(summaries=True)
    await setup_entry(hass, entry)
    coordinator = entry.runtime_data.coordinator
    a, b, c = (coordinator.data.find_story(s["id"]) for s in stories(hass))
    a.summary_status, b.summary_status, c.summary_status = "pending", "done", "pending"
    data = BrieflyData(
        sections={
            "one": Section("one", "One", "#000", [a, b, c]),
            "two": Section("two", "Two", "#000", [a]),
        },
        last_updated=dt_util.utcnow(),
    )
    assert coordinator.pending_in_priority_order(data) == [a, c]


async def test_unload_failure_keeps_cache_unsaved(hass: HomeAssistant, feeds) -> None:
    from unittest.mock import patch

    entry = make_entry()
    await setup_entry(hass, entry)
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=False):
        assert not await hass.config_entries.async_unload(entry.entry_id)
