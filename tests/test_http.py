"""Publisher etiquette: user agent, conditional GETs, robots.txt and refusals."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
import pytest

from custom_components.briefly.const import MAX_DOWNLOAD_BYTES, USER_AGENT
from custom_components.briefly.http import BrieflyHttp, host_of
from custom_components.briefly.storage import BrieflyCache

from .helpers import CONNECTION_ERROR, HTML

SITE = "https://news.example.com"
ARTICLE = f"{SITE}/story/1"


@pytest.fixture
async def client(hass: HomeAssistant, aioclient_mock) -> BrieflyHttp:
    return BrieflyHttp(async_get_clientsession(hass), BrieflyCache(hass, "t"))


async def test_feed_conditional_get(client: BrieflyHttp, aioclient_mock) -> None:
    url = f"{SITE}/rss"
    aioclient_mock.get(url, text="<rss/>", headers={"ETag": "e1", "Last-Modified": "Tue"})
    result = await client.fetch_feed(url)
    assert result.status == "ok"
    assert result.content == b"<rss/>"
    assert aioclient_mock.mock_calls[0][3]["User-Agent"] == USER_AGENT
    assert "Mozilla" not in USER_AGENT

    aioclient_mock.clear_requests()
    aioclient_mock.get(url, status=304)
    assert (await client.fetch_feed(url)).status == "not_modified"
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["If-None-Match"] == "e1"
    assert headers["If-Modified-Since"] == "Tue"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 500}, "HTTP 500"),
        ({"exc": CONNECTION_ERROR}, "Connection refused"),
        ({"exc": TimeoutError()}, "TimeoutError"),
    ],
)
async def test_feed_errors(client: BrieflyHttp, aioclient_mock, kwargs, error) -> None:
    aioclient_mock.get(f"{SITE}/rss", **kwargs)
    result = await client.fetch_feed(f"{SITE}/rss")
    assert result.status == "error"
    assert result.error == error


async def test_article_allowed(client: BrieflyHttp, aioclient_mock) -> None:
    aioclient_mock.get(f"{SITE}/robots.txt", text="User-agent: *\nDisallow: /private\n")
    aioclient_mock.get(ARTICLE, text="<p>hi</p>", headers=HTML)
    result = await client.fetch_article(ARTICLE)
    assert result.status == "ok"
    # robots.txt is cached for a day
    await client.fetch_article(ARTICLE)
    robots_calls = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("robots.txt")]
    assert len(robots_calls) == 1


async def test_article_disallowed_for_briefly(client: BrieflyHttp, aioclient_mock) -> None:
    aioclient_mock.get(
        f"{SITE}/robots.txt", text="User-agent: HomeAssistant-Briefly\nDisallow: /story\n"
    )
    assert (await client.fetch_article(ARTICLE)).status == "disallowed"


@pytest.mark.parametrize(
    ("kwargs", "allowed"),
    [({"status": 404}, True), ({"status": 503}, False), ({"exc": CONNECTION_ERROR}, False)],
)
async def test_robots_fallbacks(client: BrieflyHttp, aioclient_mock, kwargs, allowed) -> None:
    aioclient_mock.get(f"{SITE}/robots.txt", **kwargs)
    assert await client.allowed_by_robots(ARTICLE) is allowed


@pytest.mark.parametrize("status", [401, 402, 403, 429])
async def test_refusal_blocks_site_for_seven_days(
    client: BrieflyHttp, aioclient_mock, status
) -> None:
    aioclient_mock.get(f"{SITE}/robots.txt", status=404)
    aioclient_mock.get(ARTICLE, status=status)
    result = await client.fetch_article(ARTICLE)
    assert result.status == "blocked"
    assert client.site_blocked(f"{SITE}/story/2")
    aioclient_mock.clear_requests()
    assert (await client.fetch_article(f"{SITE}/story/2")).status == "blocked"
    assert aioclient_mock.call_count == 0
    assert not client._cache.host_blocked(
        "news.example.com", dt_util.utcnow() + timedelta(days=7, minutes=1)
    )


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 404}, "HTTP 404"),
        ({"exc": CONNECTION_ERROR}, "Connection refused"),
        (
            {"text": "{}", "headers": {"Content-Type": "application/json"}},
            "Not HTML: application/json",
        ),
    ],
)
async def test_article_errors(client: BrieflyHttp, aioclient_mock, kwargs, error) -> None:
    aioclient_mock.get(f"{SITE}/robots.txt", status=404)
    aioclient_mock.get(ARTICLE, **kwargs)
    result = await client.fetch_article(ARTICLE)
    assert result.status == "error"
    assert result.error == error


async def test_fetch_image(client: BrieflyHttp, aioclient_mock) -> None:
    aioclient_mock.get(f"{SITE}/a.jpg", content=b"jpg", headers={"Content-Type": "image/jpeg; q=1"})
    aioclient_mock.get(f"{SITE}/b.jpg", text="<html>", headers=HTML)
    aioclient_mock.get(f"{SITE}/c.jpg", exc=CONNECTION_ERROR)
    aioclient_mock.get(
        f"{SITE}/d.jpg",
        content=b"x" * (MAX_DOWNLOAD_BYTES + 1),
        headers={"Content-Type": "image/jpeg"},
    )
    image = await client.fetch_image(f"{SITE}/a.jpg")
    assert image.content == b"jpg"
    assert image.content_type == "image/jpeg"
    assert await client.fetch_image(f"{SITE}/b.jpg") is None
    assert await client.fetch_image(f"{SITE}/c.jpg") is None
    assert await client.fetch_image(f"{SITE}/d.jpg") is None


def test_host_of() -> None:
    assert host_of("https://WWW.Example.com/x") == "www.example.com"
    assert host_of("not a url") == ""
