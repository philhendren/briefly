"""Config and options flows (Ollama and feeds mocked)."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.briefly.config_flow import (
    hex_to_rgb,
    ollama_defaults,
    rgb_to_hex,
    split_urls,
)
from custom_components.briefly.const import DOMAIN

from .helpers import (
    CONNECTION_ERROR,
    CUSTOM_FEED,
    OLLAMA_URL,
    XML,
    FakeOllama,
    Item,
    make_entry,
    rss,
    setup_entry,
)

UK = {
    "section_name": "UK",
    "colour": [30, 136, 229],
    "feeds": ["bbc_uk", "guardian_uk"],
    "custom_feeds": "",
}


async def start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def configure(hass: HomeAssistant, result, data):
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


def options_of(result) -> list:
    return [
        o["value"] if isinstance(o, dict) else o
        for o in result["data_schema"].schema[_key(result, "feeds")].config["options"]
    ]


def _key(result, name):
    return next(k for k in result["data_schema"].schema if k == name)


def default_of(result, name):
    return _key(result, name).default()


async def test_full_flow_with_ollama(
    hass: HomeAssistant, aioclient_mock, ollama: FakeOllama
) -> None:
    aioclient_mock.get(
        CUSTOM_FEED,
        text=rss("Local Gazette", [Item("Fete", "https://example.org/fete")]),
        headers=XML,
    )
    result = await start(hass)
    result = await configure(hass, result, {"name": "Kiosk news"})
    assert result["step_id"] == "section"
    # Sources are offered as a list (radio-style), with the UK suggestion pre-ticked.
    assert "bbc_uk" in options_of(result)
    assert "sky_uk" not in options_of(result)
    assert default_of(result, "section_name") == "UK"
    assert default_of(result, "feeds") == ["bbc_uk", "guardian_uk"]

    result = await configure(hass, result, {**UK, "add_another": True})
    assert result["step_id"] == "section"
    assert default_of(result, "section_name") == "Politics"
    result = await configure(
        hass,
        result,
        {
            "section_name": "Local",
            "colour": [1, 2, 3],
            "feeds": [],
            "custom_feeds": CUSTOM_FEED,
            "add_another": False,
        },
    )
    assert result["step_id"] == "summaries"
    result = await configure(hass, result, {"summary_mode": "ollama"})
    assert result["step_id"] == "ollama"
    assert default_of(result, "ollama_url") == "http://localhost:11434"
    result = await configure(hass, result, {"ollama_url": f"{OLLAMA_URL}/"})
    assert result["step_id"] == "model"
    # Models come from Ollama itself, as a drop-down.
    model_selector = result["data_schema"].schema[_key(result, "model")]
    assert model_selector.config["options"] == ["llama3.2:3b", "qwen3:14b"]
    assert model_selector.config["mode"] == "dropdown"
    result = await configure(hass, result, {"model": "qwen3:14b", "summary_length": "short"})
    assert result["step_id"] == "voice"
    result = await configure(hass, result, {"alexa_enabled": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kiosk news"
    options = result["options"]
    assert options["ollama_url"] == OLLAMA_URL
    assert options["model"] == "qwen3:14b"
    assert [s["id"] for s in options["sections"]] == ["uk", "local"]
    assert options["sections"][1]["custom_feeds"] == [CUSTOM_FEED]
    assert options["sections"][1]["colour"] == "#010203"
    assert options["alexa_enabled"] is False


async def test_flow_without_summaries_and_with_alexa(hass: HomeAssistant, feeds) -> None:
    async_mock_service(hass, "notify", "alexa_media")
    result = await start(hass)
    result = await configure(hass, result, {"name": "Hall"})
    result = await configure(hass, result, {**UK, "add_another": False})
    result = await configure(hass, result, {"summary_mode": "off"})
    assert result["step_id"] == "voice"
    result = await configure(hass, result, {"alexa_enabled": True, "alexa_targets": []})
    assert result["errors"] == {"alexa_targets": "targets_required"}
    result = await configure(
        hass, result, {"alexa_enabled": True, "alexa_targets": ["media_player.kitchen_echo"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["alexa_targets"] == ["media_player.kitchen_echo"]
    assert result["options"]["summary_mode"] == "off"


async def test_alexa_needs_alexa_media_player(hass: HomeAssistant) -> None:
    result = await start(hass)
    result = await configure(hass, result, {"name": "Hall"})
    result = await configure(hass, result, {**UK, "add_another": False})
    result = await configure(hass, result, {"summary_mode": "off"})
    result = await configure(
        hass, result, {"alexa_enabled": True, "alexa_targets": ["media_player.echo"]}
    )
    assert result["errors"] == {"base": "alexa_media_missing"}
    assert "alexa_media_player" in result["description_placeholders"]["alexa_media_url"]


async def test_user_step_errors(hass: HomeAssistant, feeds) -> None:
    result = await start(hass)
    result = await configure(hass, result, {"name": "  "})
    assert result["errors"] == {"name": "name_required"}
    await setup_entry(hass, make_entry("Kiosk news"))
    result = await start(hass)
    result = await configure(hass, result, {"name": "Kiosk News"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("data", "errors", "mocks"),
    [
        ({"section_name": " "}, {"section_name": "name_required"}, {}),
        ({"feeds": [], "custom_feeds": ""}, {"base": "no_feeds"}, {}),
        ({"custom_feeds": "ftp://x.example/feed"}, {"custom_feeds": "invalid_url"}, {}),
        ({"custom_feeds": CUSTOM_FEED}, {"custom_feeds": "invalid_feed"}, {"status": 404}),
        (
            {"custom_feeds": CUSTOM_FEED},
            {"custom_feeds": "invalid_feed"},
            {"exc": CONNECTION_ERROR},
        ),
        (
            {"custom_feeds": CUSTOM_FEED},
            {"custom_feeds": "invalid_feed"},
            {"text": "<html>no</html>"},
        ),
        (
            {"custom_feeds": CUSTOM_FEED},
            {"custom_feeds": "invalid_feed"},
            {"text": rss("Empty", [])},
        ),
    ],
)
async def test_section_errors(hass: HomeAssistant, aioclient_mock, data, errors, mocks) -> None:
    if mocks:
        aioclient_mock.get(CUSTOM_FEED, **mocks)
    result = await start(hass)
    result = await configure(hass, result, {"name": "Desk"})
    result = await configure(hass, result, {**UK, **data, "add_another": False})
    assert result["step_id"] == "section"
    assert result["errors"] == errors
    if "custom_feeds" in errors:
        assert result["description_placeholders"]["url"] in data["custom_feeds"]
        assert default_of(result, "custom_feeds") == data["custom_feeds"]


async def test_duplicate_section_name_and_id(hass: HomeAssistant) -> None:
    result = await start(hass)
    result = await configure(hass, result, {"name": "Desk"})
    result = await configure(hass, result, {**UK, "add_another": True})
    result = await configure(hass, result, {**UK, "section_name": "uk", "add_another": True})
    assert result["errors"] == {"section_name": "name_exists"}
    result = await configure(hass, result, {**UK, "section_name": "U.K.", "add_another": True})
    result = await configure(hass, result, {**UK, "section_name": "U K", "add_another": True})
    # Past the suggestions, the form starts blank.
    assert default_of(result, "section_name") == ""
    result = await configure(hass, result, {**UK, "section_name": "Extra", "add_another": False})
    result = await configure(hass, result, {"summary_mode": "off"})
    result = await configure(hass, result, {"alexa_enabled": False})
    assert [s["id"] for s in result["options"]["sections"]] == ["uk", "u_k", "u_k_2", "extra"]


async def test_ollama_errors_and_ha_defaults(hass: HomeAssistant, aioclient_mock) -> None:
    MockConfigEntry(
        domain="ollama",
        data={"url": "http://gpu-box:11434"},
        subentries_data=[
            ConfigSubentryData(
                data={"model": "qwen3:14b"},
                subentry_type="conversation",
                title="Ollama",
                unique_id=None,
            )
        ],
    ).add_to_hass(hass)
    aioclient_mock.get("http://down:11434/api/tags", exc=CONNECTION_ERROR)
    aioclient_mock.get("http://empty:11434/api/tags", json={"models": []})
    FakeOllama(aioclient_mock, url="http://gpu-box:11434")

    result = await start(hass)
    result = await configure(hass, result, {"name": "Desk"})
    result = await configure(hass, result, {**UK, "add_another": False})
    result = await configure(hass, result, {"summary_mode": "ollama"})
    # The address of Home Assistant's own Ollama integration is filled in.
    assert default_of(result, "ollama_url") == "http://gpu-box:11434"
    assert "ollama.com" in result["description_placeholders"]["ollama_url"]
    result = await configure(hass, result, {"ollama_url": "http://down:11434"})
    assert result["errors"] == {"base": "cannot_connect"}
    result = await configure(hass, result, {"ollama_url": "http://empty:11434"})
    assert result["errors"] == {"base": "no_models"}
    result = await configure(hass, result, {"ollama_url": "http://gpu-box:11434"})
    # The model HA's Ollama integration uses is pre-selected, so no second model loads.
    assert default_of(result, "model") == "qwen3:14b"
    assert result["description_placeholders"]["ha_model"] == "qwen3:14b"


async def test_ollama_defaults_fallbacks(hass: HomeAssistant) -> None:
    assert ollama_defaults(hass) == (None, None)
    MockConfigEntry(
        domain="ollama", data={"url": "http://a:1"}, options={"model": "old:1"}
    ).add_to_hass(hass)
    assert ollama_defaults(hass) == ("http://a:1", "old:1")


def test_colour_and_url_helpers() -> None:
    assert hex_to_rgb("#ff0080") == [255, 0, 128]
    assert hex_to_rgb("nonsense") == [30, 136, 229]
    assert rgb_to_hex([300, -1, 16]) == "#ff0010"
    assert rgb_to_hex("#abcdef") == "#abcdef"
    assert rgb_to_hex("bad") == "#1e88e5"
    assert rgb_to_hex(None) == "#1e88e5"
    assert split_urls(" a,b\n c ") == ["a", "b", "c"]
    assert split_urls(None) == []


# Options flow -------------------------------------------------------------------
async def open_options(hass: HomeAssistant, entry, step: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def options_configure(hass: HomeAssistant, result, data):
    return await hass.config_entries.options.async_configure(result["flow_id"], data)


async def test_options_settings(hass: HomeAssistant, feeds) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    result = await open_options(hass, entry, "settings")
    assert result["step_id"] == "settings"
    result = await options_configure(
        hass,
        result,
        {
            "refresh_minutes": 15.0,
            "stories_per_section": 5,
            "max_age_hours": 24,
            "summaries_per_refresh": 2,
            "dedup": "strict",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["refresh_minutes"] == 15
    assert entry.options["dedup"] == "strict"
    assert entry.runtime_data.coordinator.update_interval.total_seconds() == 900


async def test_options_add_section(hass: HomeAssistant, feeds) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    result = await open_options(hass, entry, "add_section")
    result = await options_configure(
        hass, result, {**UK, "section_name": "More UK", "custom_feeds": "nope"}
    )
    assert result["errors"] == {"custom_feeds": "invalid_url"}
    result = await options_configure(hass, result, {**UK, "section_name": "More UK"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kiosk_news_more_uk") is not None


async def test_options_edit_and_remove_section(hass: HomeAssistant, feeds) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    result = await open_options(hass, entry, "edit_section")
    result = await options_configure(hass, result, {"edit_section_id": "sport"})
    assert result["step_id"] == "section_details"
    assert result["description_placeholders"]["section"] == "Sport"
    result = await options_configure(hass, result, {**UK, "section_name": "UK", "delete": False})
    assert result["errors"] == {"section_name": "name_exists"}
    result = await options_configure(
        hass, result, {**UK, "section_name": "Football", "delete": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    sections = entry.options["sections"]
    assert sections[1]["id"] == "sport"
    assert sections[1]["section_name"] == "Football"

    result = await open_options(hass, entry, "edit_section")
    result = await options_configure(hass, result, {"edit_section_id": "uk"})
    result = await options_configure(hass, result, {**UK, "delete": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert [s["id"] for s in entry.options["sections"]] == ["sport"]

    result = await open_options(hass, entry, "edit_section")
    result = await options_configure(hass, result, {"edit_section_id": "sport"})
    result = await options_configure(hass, result, {**UK, "delete": True})
    assert result["errors"] == {"base": "last_section"}


async def test_options_no_sections(hass: HomeAssistant, feeds) -> None:
    entry = make_entry(sections=[])
    await setup_entry(hass, entry)
    result = await open_options(hass, entry, "edit_section")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_sections"


async def test_options_summaries_and_voice(hass: HomeAssistant, feeds, ollama: FakeOllama) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    result = await open_options(hass, entry, "summaries")
    result = await options_configure(hass, result, {"summary_mode": "ollama"})
    result = await options_configure(hass, result, {"ollama_url": OLLAMA_URL})
    result = await options_configure(
        hass, result, {"model": "llama3.2:3b", "summary_length": "headline"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.options["model"] == "llama3.2:3b"
    assert entry.runtime_data.coordinator.summaries_enabled
    assert "one sentence" in ollama.requests[0]["messages"][1]["content"]

    # Re-opening keeps the chosen model selected.
    result = await open_options(hass, entry, "summaries")
    result = await options_configure(hass, result, {"summary_mode": "ollama"})
    result = await options_configure(hass, result, {"ollama_url": OLLAMA_URL})
    assert default_of(result, "model") == "llama3.2:3b"

    result = await open_options(hass, entry, "summaries")
    result = await options_configure(hass, result, {"summary_mode": "off"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert not entry.runtime_data.coordinator.summaries_enabled

    async_mock_service(hass, "notify", "alexa_media")
    result = await open_options(hass, entry, "voice")
    result = await options_configure(
        hass, result, {"alexa_enabled": True, "alexa_targets": ["media_player.kitchen_echo"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["alexa_enabled"] is True
