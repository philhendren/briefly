"""Setting up, refreshing and unloading a news desk."""

from __future__ import annotations

from datetime import timedelta

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import BBC_UK, make_entry, setup_entry


async def test_setup_creates_section_sensors(hass: HomeAssistant, feeds) -> None:
    """Each section becomes a sensor whose state is its story count."""
    entry = make_entry()
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    uk = hass.states.get("sensor.kiosk_news_uk")
    assert uk.state == "3"  # homes (deduped with Guardian), rail, museum
    titles = [s["title"] for s in uk.attributes["stories"]]
    assert titles[0] == "Council approves 250 new homes on town edge"
    assert "Very old story that should be filtered out" not in titles
    lead = uk.attributes["stories"][0]
    assert lead["also_reported_by"] == ["The Guardian"]
    assert lead["summary_status"] == "off"
    assert lead["image"].startswith("/api/briefly/image/")
    assert uk.attributes["sources"] == ["BBC News", "The Guardian"]
    assert uk.attributes["colour"] == "#1e88e5"

    assert hass.states.get("sensor.kiosk_news_sport").state == "1"  # cup final deduped
    assert hass.states.get("sensor.kiosk_news_last_updated") is not None
    assert hass.states.get("button.kiosk_news_refresh") is not None
    assert hass.states.get("event.kiosk_news_new_story") is not None


async def test_conditional_refresh(hass: HomeAssistant, feeds) -> None:
    """A second refresh sends the stored ETag."""
    entry = make_entry()
    await setup_entry(hass, entry)
    feeds.mock_calls.clear()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done(wait_background_tasks=True)
    bbc = [c for c in feeds.mock_calls if str(c[1]) == BBC_UK]
    assert bbc and bbc[0][3]["If-None-Match"] == '"bbc1"'
