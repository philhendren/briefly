"""Services, including spoken headlines through a mocked Alexa Media Player."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.briefly.const import DOMAIN

from .helpers import FakeOllama, make_entry, setup_entry


async def call(hass: HomeAssistant, service: str, data: dict | None = None, response: bool = False):
    return await hass.services.async_call(
        DOMAIN, service, data or {}, blocking=True, return_response=response
    )


async def test_get_stories(hass: HomeAssistant, feeds) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    result = await call(hass, "get_stories", {"count": 3}, response=True)
    # Round-robin: UK lead, Sport lead, then UK second.
    assert [s["section"] for s in result["stories"]] == ["UK", "Sport", "UK"]
    assert result["stories"][0]["colour"] == "#1e88e5"

    uk = await call(
        hass, "get_stories", {"section": "uk", "count": 10, "config_entry_id": entry.entry_id}, response=True
    )
    assert len(uk["stories"]) == 3 and {s["section"] for s in uk["stories"]} == {"UK"}

    with pytest.raises(ServiceValidationError, match="section_not_found|No section"):
        await call(hass, "get_stories", {"section": "Weather"}, response=True)


async def test_service_errors_without_desks(hass: HomeAssistant, feeds) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    with pytest.raises(ServiceValidationError):
        await call(hass, "refresh", {"config_entry_id": "missing"})
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await call(hass, "refresh")


async def test_refresh_service(hass: HomeAssistant, feeds) -> None:
    await setup_entry(hass, make_entry())
    feeds.mock_calls.clear()
    await call(hass, "refresh")
    await hass.async_block_till_done()
    assert feeds.call_count > 0


async def test_summarise_service(hass: HomeAssistant, feeds, ollama: FakeOllama) -> None:
    ollama.replies = [503] * 4  # the automatic pass fails once for every story
    entry = make_entry(summaries=True)
    await setup_entry(hass, entry)
    story_id = hass.states.get("sensor.kiosk_news_uk").attributes["stories"][0]["id"]
    result = await call(hass, "summarise", {"story_id": story_id}, response=True)
    assert result["story"]["summary_status"] == "done"
    state = hass.states.get("sensor.kiosk_news_uk").attributes["stories"][0]
    assert state["summary_status"] == "done"
    # Already done: no new request.
    count = len(ollama.requests)
    await call(hass, "summarise", {"story_id": story_id}, response=True)
    assert len(ollama.requests) == count

    with pytest.raises(ServiceValidationError):
        await call(hass, "summarise", {"story_id": "nope"}, response=True)


async def test_summarise_service_when_off(hass: HomeAssistant, feeds) -> None:
    await setup_entry(hass, make_entry())
    story_id = hass.states.get("sensor.kiosk_news_uk").attributes["stories"][0]["id"]
    with pytest.raises(ServiceValidationError):
        await call(hass, "summarise", {"story_id": story_id}, response=True)


async def test_speak_headlines(hass: HomeAssistant, feeds) -> None:
    calls = async_mock_service(hass, "notify", "alexa_media")
    await setup_entry(hass, make_entry(alexa=True))
    await call(hass, "speak_headlines", {"section": "UK", "count": 2})
    assert len(calls) == 1
    data = calls[0].data
    assert data["target"] == ["media_player.kitchen_echo"]
    assert data["data"] == {"type": "tts"}
    assert data["message"].startswith("Here are the top 2 headlines from UK news.")
    assert "From BBC News: Council approves 250 new homes on town edge." in data["message"]

    await call(hass, "speak_headlines", {"targets": ["media_player.lounge_echo"], "count": 1})
    assert calls[1].data["target"] == ["media_player.lounge_echo"]
    assert calls[1].data["message"].startswith("Here is the top headline from Kiosk news.")


async def test_speak_headlines_errors(hass: HomeAssistant, feeds) -> None:
    off = make_entry("Hall news")
    await setup_entry(hass, off)
    with pytest.raises(ServiceValidationError, match="alexa_disabled|switched off"):
        await call(hass, "speak_headlines", {"config_entry_id": off.entry_id})

    on = make_entry(alexa=True)
    on.add_to_hass(hass)
    hass.config_entries.async_update_entry(on, options={**on.options, "alexa_targets": []})
    await hass.config_entries.async_setup(on.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError, match="alexa_no_targets|Echo"):
        await call(hass, "speak_headlines", {"config_entry_id": on.entry_id})

    # Alexa Media Player is not installed: a clear error, not a crash.
    with pytest.raises(ServiceValidationError, match="alexa_media_missing|Alexa Media Player"):
        await call(
            hass,
            "speak_headlines",
            {"config_entry_id": on.entry_id, "targets": ["media_player.kitchen_echo"]},
        )
