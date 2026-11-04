"""Shared BDD steps.

pytest-bdd steps are synchronous, so each step drives Home Assistant's event
loop with `run(...)`. All HTTP (feeds, articles, Ollama) is mocked.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, then, when
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.briefly.const import DOMAIN

from ..helpers import register_feeds


def run(hass: HomeAssistant, coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine on Home Assistant's loop from a synchronous step."""
    return hass.loop.run_until_complete(coro)


def settle(hass: HomeAssistant) -> None:
    """Wait for refreshes and background summaries to finish."""
    run(hass, hass.async_block_till_done(wait_background_tasks=True))


@pytest.fixture
def ctx() -> dict[str, Any]:
    """Scenario state shared between steps."""
    return {}


def ensure_feeds(ctx: dict[str, Any], aioclient_mock) -> None:
    """Register the standard feeds once, after any scenario-specific overrides."""
    if ctx.get("feeds_wanted") and not ctx.get("feeds_registered"):
        register_feeds(aioclient_mock)
        ctx["feeds_registered"] = True


def start_flow(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, name: str) -> None:
    ensure_feeds(ctx, aioclient_mock)
    result = run(
        hass,
        hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}),
    )
    ctx["result"] = run(hass, hass.config_entries.flow.async_configure(result["flow_id"], {"name": name}))


def configure(hass: HomeAssistant, ctx: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    ctx["result"] = run(
        hass, hass.config_entries.flow.async_configure(ctx["result"]["flow_id"], data)
    )
    return ctx["result"]


def setup_desk(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, entry) -> None:
    ensure_feeds(ctx, aioclient_mock)
    entry.add_to_hass(hass)
    run(hass, hass.config_entries.async_setup(entry.entry_id))
    settle(hass)
    ctx["entry"] = entry


def refresh(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    settle(hass)


UK_SECTION = {
    "section_name": "UK",
    "colour": [30, 136, 229],
    "feeds": ["bbc_uk", "guardian_uk"],
    "custom_feeds": "",
    "add_another": False,
}


@given("the standard news feeds are available")
def standard_feeds(ctx: dict[str, Any]) -> None:
    ctx["feeds_wanted"] = True


@when(parsers.parse('I start setting up a news desk called "{name}"'))
def start_setup(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, name: str) -> None:
    start_flow(hass, ctx, aioclient_mock, name)


@then(parsers.parse('the form shows the error "{error}"'))
def form_error(ctx: dict[str, Any], error: str) -> None:
    assert error in ctx["result"]["errors"].values()


@then(parsers.parse('the form shows the error "{error}" for "{field}"'))
def form_field_error(ctx: dict[str, Any], error: str, field: str) -> None:
    assert ctx["result"]["errors"][field] == error
