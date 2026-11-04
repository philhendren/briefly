"""BDD: spoken headlines through a mocked Alexa Media Player."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.briefly.const import DOMAIN

from ..helpers import make_entry
from .conftest import UK_SECTION, configure, run, setup_desk, start_flow

scenarios("spoken_headlines.feature")


@given("Alexa Media Player is installed")
def alexa_installed(hass: HomeAssistant, ctx: dict[str, Any]) -> None:
    ctx["alexa_calls"] = async_mock_service(hass, "notify", "alexa_media")


@given("Alexa Media Player is not installed")
def alexa_missing(hass: HomeAssistant) -> None:
    assert not hass.services.has_service("notify", "alexa_media")


@given(parsers.parse('a news desk with spoken headlines on "{entity_id}"'))
def desk_with_alexa(
    hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, entity_id: str
) -> None:
    entry = make_entry(alexa=True, override={"alexa_targets": [entity_id]})
    setup_desk(hass, ctx, aioclient_mock, entry)


@given("a news desk without spoken headlines")
def desk_without_alexa(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock) -> None:
    setup_desk(hass, ctx, aioclient_mock, make_entry())


def speak(hass: HomeAssistant, data: dict[str, Any]) -> None:
    run(hass, hass.services.async_call(DOMAIN, "speak_headlines", data, blocking=True))


@when(parsers.parse('I ask Briefly to speak {count:d} headlines from "{section}"'))
def ask(hass: HomeAssistant, count: int, section: str) -> None:
    speak(hass, {"count": count, "section": section})


@when("I try to ask Briefly to speak headlines")
def try_ask(hass: HomeAssistant, ctx: dict[str, Any]) -> None:
    try:
        speak(hass, {})
    except ServiceValidationError as err:
        ctx["error"] = err


@when("I try to turn on spoken headlines while setting up a news desk")
def try_enable(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock) -> None:
    start_flow(hass, ctx, aioclient_mock, "Kiosk news")
    configure(hass, ctx, UK_SECTION)
    configure(hass, ctx, {"summary_mode": "off"})
    configure(hass, ctx, {"alexa_enabled": True, "alexa_targets": ["media_player.kitchen_echo"]})


@then(parsers.parse('Alexa is asked to say "{text}" on "{entity_id}"'))
def said_on(ctx: dict[str, Any], text: str, entity_id: str) -> None:
    call = ctx["alexa_calls"][-1]
    assert text in call.data["message"]
    assert call.data["target"] == [entity_id]
    assert call.data["data"] == {"type": "tts"}


@then(parsers.parse('Alexa is asked to say "{text}"'))
def said(ctx: dict[str, Any], text: str) -> None:
    assert text in ctx["alexa_calls"][-1].data["message"]


@then(parsers.parse('the form links to "{url}"'))
def links(ctx: dict[str, Any], url: str) -> None:
    assert url in ctx["result"]["description_placeholders"].values()


@then("I am told spoken headlines are switched off")
def told_off(ctx: dict[str, Any]) -> None:
    assert ctx["error"].translation_key == "alexa_disabled"
