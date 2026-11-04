"""The Ollama client, against a mocked server."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest

from custom_components.briefly.ollama import (
    SUMMARY_SCHEMA,
    OllamaError,
    OllamaSummariser,
    Summary,
    async_list_models,
    build_messages,
    numbers_supported,
    parse_summary,
)

from .helpers import CONNECTION_ERROR, OLLAMA_URL, FakeOllama


async def test_list_models(hass: HomeAssistant, ollama: FakeOllama) -> None:
    session = async_get_clientsession(hass)
    assert await async_list_models(session, f"{OLLAMA_URL}/") == ["llama3.2:3b", "qwen3:14b"]


@pytest.mark.parametrize(
    ("kwargs"),
    [
        {"status": 500},
        {"exc": CONNECTION_ERROR},
        {"json": {"unexpected": True}},
        {"json": ["not", "a", "dict"]},
        {"text": "not json"},
    ],
)
async def test_list_models_errors(hass: HomeAssistant, aioclient_mock, kwargs) -> None:
    aioclient_mock.get(f"{OLLAMA_URL}/api/tags", **kwargs)
    with pytest.raises(OllamaError):
        await async_list_models(async_get_clientsession(hass), OLLAMA_URL)


async def test_list_models_skips_nameless(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(
        f"{OLLAMA_URL}/api/tags",
        json={"models": [{"model": "a:1"}, {}, "junk"]},
    )
    assert await async_list_models(async_get_clientsession(hass), OLLAMA_URL) == ["a:1"]


async def test_summarise_sends_structured_request(hass: HomeAssistant, ollama: FakeOllama) -> None:
    ollama.replies.append({"summary": ["One.", "Two."], "key_facts": ["Fact"]})
    summariser = OllamaSummariser(async_get_clientsession(hass), OLLAMA_URL, "qwen3:14b", "medium")
    summary = await summariser.async_summarise("Headline", "Article text")
    assert summary == Summary(["One.", "Two."], ["Fact"])
    request = ollama.requests[0]
    assert request["model"] == "qwen3:14b"
    assert request["stream"] is False
    assert request["think"] is False
    assert request["format"] == SUMMARY_SCHEMA
    assert "150 to 220 words" in request["messages"][1]["content"]
    assert "Use only facts stated in the article" in request["messages"][0]["content"]


@pytest.mark.parametrize("reply", [503, CONNECTION_ERROR, "garbage"])
async def test_summarise_errors(hass: HomeAssistant, ollama: FakeOllama, reply) -> None:
    ollama.replies.append(reply)
    summariser = OllamaSummariser(async_get_clientsession(hass), OLLAMA_URL, "m")
    with pytest.raises(OllamaError):
        await summariser.async_summarise("t", "a")


async def test_summarise_unexpected_payload(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(f"{OLLAMA_URL}/api/chat", json={"done": True})
    summariser = OllamaSummariser(async_get_clientsession(hass), OLLAMA_URL, "m")
    with pytest.raises(OllamaError):
        await summariser.async_summarise("t", "a")


def test_parse_summary_variants() -> None:
    assert parse_summary('{"summary": "One line", "key_facts": ["a", " ", "b", "c", "d"]}') == (
        Summary(["One line"], ["a", "b", "c"])
    )
    assert parse_summary('{"summary": ["x"]}') == Summary(["x"], [])
    for bad in (
        "nope",
        "[1, 2]",
        '{"summary": 5}',
        '{"summary": ["x"], "key_facts": "y"}',
        '{"summary": [" "]}',
    ):
        with pytest.raises(OllamaError):
            parse_summary(bad)


def test_build_messages_unknown_length_falls_back_to_short() -> None:
    messages = build_messages("Title", "Body", "enormous")
    assert "90 to 140 words" in messages[1]["content"]
    assert "Headline: Title" in messages[1]["content"]


def test_numbers_supported() -> None:
    source = "The council approved 250 homes and £1,200,000 for roads in 2026."
    assert numbers_supported(Summary(["250 homes", "£1200000 roads"], ["2026"]), source)
    assert not numbers_supported(Summary(["300 homes"], []), source)
    assert numbers_supported(Summary(["No numbers at all"], []), source)
