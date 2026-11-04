"""Test helpers: feed builders, article pages and a fake Ollama server.

Nothing here touches the network: every HTTP call goes through Home
Assistant's AiohttpClientMocker, and pytest-socket blocks real sockets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from email.utils import format_datetime
import json
from typing import Any
from xml.sax.saxutils import escape

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.briefly.const import (
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_TARGETS,
    CONF_COLOUR,
    CONF_CUSTOM_FEEDS,
    CONF_FEEDS,
    CONF_MODEL,
    CONF_NAME,
    CONF_OLLAMA_URL,
    CONF_SECTION_ID,
    CONF_SECTION_NAME,
    CONF_SECTIONS,
    CONF_SUMMARY_LENGTH,
    CONF_SUMMARY_MODE,
    DEFAULT_SETTINGS,
    DOMAIN,
    SUMMARY_OFF,
    SUMMARY_OLLAMA,
)
from custom_components.briefly.sources import PRESET_FEEDS

OLLAMA_URL = "http://ollama.local:11434"
BBC_UK = PRESET_FEEDS["bbc_uk"].url
GUARDIAN_UK = PRESET_FEEDS["guardian_uk"].url
BBC_SPORT = PRESET_FEEDS["bbc_sport"].url
GUARDIAN_SPORT = PRESET_FEEDS["guardian_sport"].url
CUSTOM_FEED = "https://example.org/news.xml"

HTML = {"Content-Type": "text/html; charset=utf-8"}
XML = {"Content-Type": "application/rss+xml"}


@dataclass
class Item:
    """One feed item."""

    title: str
    link: str
    description: str = "A short description of the story from the feed."
    age_minutes: int = 10
    thumbnail: tuple[str, int] | None = None
    media: list[tuple[str, int | None]] = field(default_factory=list)
    enclosure: str | None = None


def rss(title: str, items: list[Item]) -> str:
    """Return an RSS 2.0 document."""
    now = dt_util.utcnow()
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>',
        f"<title>{escape(title)}</title><link>https://example.com/</link>",
    ]
    for item in items:
        published = format_datetime(now - timedelta(minutes=item.age_minutes), usegmt=True)
        parts.append(
            f"<item><title>{escape(item.title)}</title><link>{escape(item.link)}</link>"
            f"<description>{escape(item.description)}</description>"
            f"<pubDate>{published}</pubDate>"
        )
        if item.thumbnail:
            parts.append(
                f'<media:thumbnail width="{item.thumbnail[1]}" url="{escape(item.thumbnail[0])}"/>'
            )
        for url, width in item.media:
            # Guardian style: url and width only. Without a width, say it is an image.
            attrs = f' width="{width}"' if width else ' medium="image"'
            parts.append(f'<media:content url="{escape(url)}"{attrs}/>')
        if item.enclosure:
            parts.append(
                f'<enclosure url="{escape(item.enclosure)}" type="image/jpeg" length="1"/>'
            )
        parts.append("</item>")
    parts.append("</channel></rss>")
    return "".join(parts)


def atom(title: str, items: list[Item]) -> str:
    """Return an Atom document."""
    now = dt_util.utcnow()
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<feed xmlns="http://www.w3.org/2005/Atom"><title>{escape(title)}</title>',
    ]
    for item in items:
        updated = (now - timedelta(minutes=item.age_minutes)).isoformat()
        parts.append(
            f"<entry><title>{escape(item.title)}</title>"
            f'<link href="{escape(item.link)}"/><id>{escape(item.link)}</id>'
            f"<updated>{updated}</updated><summary>{escape(item.description)}</summary></entry>"
        )
    parts.append("</feed>")
    return "".join(parts)


def article_html(paragraphs: list[str]) -> str:
    """Return a realistic article page."""
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    return (
        "<html><head><title>Story</title><script>var x = 1;</script></head><body>"
        "<nav><p>Home News Sport Weather iPlayer Sounds Bitesize and more links</p></nav>"
        f"<article><h1>Story</h1>{body}</article>"
        "<footer><p>Copyright notice and other footer text that is long enough.</p></footer>"
        "</body></html>"
    )


# Standard news ---------------------------------------------------------------
HOMES_PARAS = [
    "The council has approved plans for 250 new homes on the edge of the town, "
    "following a vote on Tuesday evening.",
    "Councillors voted 7 to 2 in favour of the scheme, which includes a new primary "
    "school and a health centre.",
    "Residents had raised concerns about traffic, and the developer has agreed to pay "
    "£1,200,000 towards road improvements.",
    "Work is expected to start next spring and take about three years to complete.",
]
RAIL_PARAS = [
    "Rail passengers face disruption this weekend as engineering works close the main "
    "line between the two cities.",
    "Replacement buses will run between the stations, adding up to 45 minutes to journeys.",
    "The operator apologised and said the work was needed to replace ageing track.",
]


def bbc_uk_feed() -> str:
    """Return the standard BBC UK feed."""
    return rss(
        "BBC News",
        [
            Item(
                "Council approves 250 new homes on town edge",
                "https://www.bbc.co.uk/news/articles/homes1?at_medium=RSS&at_campaign=rss",
                "Plans include a school and a health centre.",
                age_minutes=5,
                thumbnail=(
                    "https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/aaa/live/homes.jpg",
                    240,
                ),
            ),
            Item(
                "Weekend rail disruption as main line closes",
                "https://www.bbc.co.uk/news/articles/rail1",
                "Engineering works will close the line.",
                age_minutes=30,
                thumbnail=(
                    "https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/bbb/live/rail.jpg",
                    240,
                ),
            ),
            Item(
                "Very old story that should be filtered out",
                "https://www.bbc.co.uk/news/articles/old1",
                age_minutes=60 * 24 * 5,
            ),
        ],
    )


def guardian_uk_feed() -> str:
    """Return the standard Guardian UK feed, which repeats the homes story."""
    return rss(
        "The Guardian",
        [
            Item(
                "Council approves 250 new homes on edge of town | Jane Writer",
                "https://www.theguardian.com/uk-news/2026/nov/04/homes",
                "<p>Plans approved after a vote.</p> <a href='x'>Continue reading...</a>",
                age_minutes=8,
                media=[
                    ("https://i.guim.co.uk/img/homes-140.jpg", 140),
                    ("https://i.guim.co.uk/img/homes-460.jpg", 460),
                ],
            ),
            Item(
                "Museum reopens after two-year restoration",
                "https://www.theguardian.com/culture/2026/nov/04/museum",
                "<p>The museum has reopened.</p>",
                age_minutes=45,
            ),
        ],
    )


def sport_feed(source: str, slug: str) -> str:
    """Return a small sport feed."""
    return rss(
        source,
        [
            Item(
                f"Local club wins cup final in {slug} thriller",
                f"https://sport.example.com/{slug}/cup",
                age_minutes=12,
            )
        ],
    )


def register_feeds(aioclient_mock: AiohttpClientMocker) -> None:
    """Register the standard feeds, robots.txt files and articles."""
    aioclient_mock.get(BBC_UK, text=bbc_uk_feed(), headers={**XML, "ETag": '"bbc1"'})
    aioclient_mock.get(GUARDIAN_UK, text=guardian_uk_feed(), headers=XML)
    aioclient_mock.get(BBC_SPORT, text=sport_feed("BBC Sport", "bbc"), headers=XML)
    aioclient_mock.get(GUARDIAN_SPORT, text=sport_feed("Guardian Sport", "guardian"), headers=XML)
    aioclient_mock.get("https://www.bbc.co.uk/robots.txt", text="User-agent: *\nDisallow: /cbbc\n")
    aioclient_mock.get("https://www.theguardian.com/robots.txt", text="User-agent: *\nAllow: /\n")
    aioclient_mock.get("https://sport.example.com/robots.txt", status=404)
    aioclient_mock.get(
        "https://www.bbc.co.uk/news/articles/homes1", text=article_html(HOMES_PARAS), headers=HTML
    )
    aioclient_mock.get(
        "https://www.bbc.co.uk/news/articles/rail1", text=article_html(RAIL_PARAS), headers=HTML
    )
    aioclient_mock.get(
        "https://www.theguardian.com/culture/2026/nov/04/museum",
        text=article_html(
            [
                "The city museum has reopened to visitors after a two-year restoration "
                "project costing millions.",
                "New galleries show the history of the region, and entry remains free.",
                "The director said she hoped families would return in large numbers.",
            ]
        ),
        headers=HTML,
    )
    for slug in ("bbc", "guardian"):
        aioclient_mock.get(
            f"https://sport.example.com/{slug}/cup",
            text=article_html(
                [
                    "The local club won the cup final in a thrilling match that went to "
                    "extra time on Saturday afternoon.",
                    "The winning goal came in the final minute, sparking celebrations "
                    "among the travelling supporters.",
                    "The manager praised his players for their resilience and spirit.",
                ]
            ),
            headers=HTML,
        )


# Fake Ollama -------------------------------------------------------------------
CONNECTION_ERROR = aiohttp.ClientConnectionError("Connection refused")
Reply = dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]


class FakeOllama:
    """A scripted Ollama server behind AiohttpClientMocker.

    `replies` is a queue; each entry is either a JSON object the model "writes",
    an int HTTP status, an exception to raise, or the string "garbage" for a
    non-JSON reply. When the queue is empty, `default` is used.
    """

    def __init__(
        self,
        aioclient_mock: AiohttpClientMocker,
        url: str = OLLAMA_URL,
        models: list[str] | None = None,
    ) -> None:
        """Register the fake endpoints."""
        self.url = url
        self.models = ["llama3.2:3b", "qwen3:14b"] if models is None else models
        self.requests: list[dict[str, Any]] = []
        self.replies: list[Any] = []
        self.offline = False
        self.default: Reply = self._echo_summary
        aioclient_mock.get(f"{url}/api/tags", side_effect=self._tags)
        aioclient_mock.post(f"{url}/api/chat", side_effect=self._chat)

    @staticmethod
    def _echo_summary(request: dict[str, Any]) -> dict[str, Any]:
        """Summarise faithfully: reuse the first article sentence."""
        article = request["messages"][1]["content"].split("Article:\n", 1)[1]
        first = article.split("\n\n")[0]
        return {"summary": [first], "key_facts": [first.split(",")[0]]}

    async def _tags(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        if self.offline:
            return AiohttpClientMockResponse(method, url, exc=CONNECTION_ERROR)
        return AiohttpClientMockResponse(
            method,
            url,
            json={"models": [{"name": m, "model": m} for m in self.models]},
        )

    async def _chat(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        self.requests.append(data)
        if self.offline:
            return AiohttpClientMockResponse(method, url, exc=CONNECTION_ERROR)
        reply = self.replies.pop(0) if self.replies else self.default
        if isinstance(reply, BaseException):
            return AiohttpClientMockResponse(method, url, exc=reply)
        if isinstance(reply, int):
            return AiohttpClientMockResponse(method, url, status=reply)
        if reply == "garbage":
            content = "this is not json"
        else:
            content = json.dumps(reply(data) if callable(reply) else reply)
        return AiohttpClientMockResponse(
            method,
            url,
            json={"model": data["model"], "message": {"role": "assistant", "content": content}},
        )


# Config entries -----------------------------------------------------------------
def sections_uk_sport(custom: list[str] | None = None) -> list[dict[str, Any]]:
    """Return two standard sections."""
    return [
        {
            CONF_SECTION_ID: "uk",
            CONF_SECTION_NAME: "UK",
            CONF_COLOUR: "#1e88e5",
            CONF_FEEDS: ["bbc_uk", "guardian_uk"],
            CONF_CUSTOM_FEEDS: custom or [],
        },
        {
            CONF_SECTION_ID: "sport",
            CONF_SECTION_NAME: "Sport",
            CONF_COLOUR: "#43a047",
            CONF_FEEDS: ["bbc_sport", "guardian_sport"],
            CONF_CUSTOM_FEEDS: [],
        },
    ]


def entry_options(
    *,
    summaries: bool = False,
    alexa: bool = False,
    sections: list[dict[str, Any]] | None = None,
    **settings: Any,
) -> dict[str, Any]:
    """Return config entry options."""
    options: dict[str, Any] = {
        **DEFAULT_SETTINGS,
        **settings,
        CONF_SECTIONS: sections if sections is not None else sections_uk_sport(),
        CONF_SUMMARY_MODE: SUMMARY_OLLAMA if summaries else SUMMARY_OFF,
        CONF_ALEXA_ENABLED: alexa,
        CONF_ALEXA_TARGETS: ["media_player.kitchen_echo"] if alexa else [],
    }
    if summaries:
        options |= {
            CONF_OLLAMA_URL: OLLAMA_URL,
            CONF_MODEL: "qwen3:14b",
            CONF_SUMMARY_LENGTH: "short",
        }
    return options


def make_entry(title: str = "Kiosk news", override: dict[str, Any] | None = None, **kwargs: Any):
    """Return a MockConfigEntry for a news desk; `override` replaces option keys."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=title.lower().replace(" ", "_"),
        data={CONF_NAME: title},
        options={**entry_options(**kwargs), **(override or {})},
    )


async def setup_entry(hass: HomeAssistant, entry) -> None:
    """Add and set up an entry, waiting for background summaries."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
