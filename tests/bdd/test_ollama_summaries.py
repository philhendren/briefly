"""BDD: optional Ollama summaries, against a fake Ollama server."""

from __future__ import annotations

import re
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from homeassistant.core import HomeAssistant

from ..helpers import FakeOllama, make_entry
from .conftest import UK_SECTION, configure, refresh, setup_desk, start_flow

scenarios("ollama_summaries.feature")


@given(parsers.parse('an Ollama server with the models "{models}"'))
def ollama_server(ctx: dict[str, Any], aioclient_mock, models: str) -> None:
    ctx["ollama"] = FakeOllama(aioclient_mock, models=[m.strip() for m in models.split(",")])


@given("Ollama is unreachable")
def ollama_offline(ctx: dict[str, Any]) -> None:
    ctx["ollama"].offline = True


@given(parsers.parse("Ollama invents the number {number:d} in every summary"))
def ollama_invents(ctx: dict[str, Any], number: int) -> None:
    ctx["ollama"].default = {"summary": [f"The council approved {number} homes."], "key_facts": []}


@given(parsers.parse('"{host}" refuses article requests with HTTP {status:d}'))
def publisher_refuses(aioclient_mock, host: str, status: int) -> None:
    aioclient_mock.get(re.compile(rf"^https://{re.escape(host)}/news/"), status=status)


@given(parsers.parse('a news desk with summaries written by "{model}"'))
def desk_with_summaries(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, model: str) -> None:
    setup_desk(hass, ctx, aioclient_mock, make_entry(summaries=True, override={"model": model}))


@given(parsers.parse('a news desk with "{length}" summaries written by "{model}"'))
def desk_with_length(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, length: str, model: str) -> None:
    entry = make_entry(summaries=True, override={"model": model, "summary_length": length})
    setup_desk(hass, ctx, aioclient_mock, entry)


@when(parsers.parse('I set up summaries with Ollama at "{url}"'))
def set_up_summaries(hass: HomeAssistant, ctx: dict[str, Any], aioclient_mock, url: str) -> None:
    start_flow(hass, ctx, aioclient_mock, "Kiosk news")
    configure(hass, ctx, UK_SECTION)
    configure(hass, ctx, {"summary_mode": "ollama"})
    configure(hass, ctx, {"ollama_url": url})


@when(parsers.parse("the news desk refreshes {times:d} more times"))
def refreshes(hass: HomeAssistant, times: int) -> None:
    for _ in range(times):
        refresh(hass)


def story(hass: HomeAssistant, prefix: str) -> dict[str, Any]:
    stories = hass.states.get("sensor.kiosk_news_uk").attributes["stories"]
    return next(s for s in stories if s["title"].startswith(prefix))


@then(parsers.parse('the model drop-down offers "{models}"'))
def model_dropdown(ctx: dict[str, Any], models: str) -> None:
    result = ctx["result"]
    assert result["step_id"] == "model"
    schema = result["data_schema"].schema
    selector = schema[next(key for key in schema if key == "model")]
    assert selector.config["mode"] == "dropdown"
    assert selector.config["options"] == [m.strip() for m in models.split(",")]


@then(parsers.parse('the story "{prefix}" has summary status "{status}"'))
def summary_status(hass: HomeAssistant, prefix: str, status: str) -> None:
    assert story(hass, prefix)["summary_status"] == status


@then(parsers.parse('the summary of "{prefix}" mentions "{text}"'))
def summary_mentions(hass: HomeAssistant, prefix: str, text: str) -> None:
    assert text in " ".join(story(hass, prefix)["summary"])


@then(parsers.parse('the story "{prefix}" shows its feed description'))
def feed_description(hass: HomeAssistant, prefix: str) -> None:
    found = story(hass, prefix)
    assert found["summary"] == [] and found["description"]


@then(parsers.parse('Ollama was asked to use the model "{model}" with structured output'))
def asked_model(ctx: dict[str, Any], model: str) -> None:
    request = ctx["ollama"].requests[0]
    assert request["model"] == model
    assert request["format"]["required"] == ["summary", "key_facts"]
    assert request["stream"] is False


@then(parsers.parse('Ollama was asked for "{words}"'))
def asked_words(ctx: dict[str, Any], words: str) -> None:
    assert words in ctx["ollama"].requests[0]["messages"][1]["content"]


@then("Ollama receives no more requests when the desk refreshes again")
def no_more_requests(hass: HomeAssistant, ctx: dict[str, Any]) -> None:
    before = len(ctx["ollama"].requests)
    refresh(hass)
    assert len(ctx["ollama"].requests) == before


@then(parsers.parse('no request was made for "{url}"'))
def no_request(aioclient_mock, url: str) -> None:
    assert not [call for call in aioclient_mock.mock_calls if str(call[1]) == url]
