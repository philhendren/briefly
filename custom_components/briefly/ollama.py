"""Talk to an Ollama server: list models and write story summaries."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import aiohttp

from .const import (
    HTTP_TIMEOUT,
    LENGTH_HEADLINE,
    LENGTH_MEDIUM,
    LENGTH_SHORT,
    OLLAMA_TIMEOUT,
)

LENGTH_RULES = {
    LENGTH_HEADLINE: "Write one sentence of no more than 30 words.",
    LENGTH_SHORT: "Write 2 or 3 short paragraphs, 90 to 140 words in total.",
    LENGTH_MEDIUM: "Write 3 or 4 short paragraphs, 150 to 220 words in total.",
}

SYSTEM_PROMPT = (
    "You summarise news articles for a family news screen. Rules: "
    "Use only facts stated in the article. No background, opinion or speculation. "
    "British English, plain and neutral. "
    "Keep names, numbers and quotes exactly as written. "
    "Reply with JSON only."
)

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "key_facts": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["summary", "key_facts"],
}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class OllamaError(Exception):
    """Raised when Ollama cannot be reached or replies with something unusable."""


@dataclass(slots=True)
class Summary:
    """A validated story summary."""

    paragraphs: list[str]
    key_facts: list[str]


def normalise_url(url: str) -> str:
    """Return the Ollama base URL without a trailing slash."""
    return url.strip().rstrip("/")


async def async_list_models(session: aiohttp.ClientSession, url: str) -> list[str]:
    """Return the names of the models installed on an Ollama server."""
    try:
        async with session.get(
            f"{normalise_url(url)}/api/tags",
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                raise OllamaError(f"Ollama replied {resp.status}")
            payload = await resp.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise OllamaError(str(err)) from err
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise OllamaError("Unexpected reply from Ollama")
    names = {m.get("name") or m.get("model") for m in models if isinstance(m, dict)}
    return sorted(name for name in names if name)


def build_messages(title: str, article: str, length: str) -> list[dict[str, str]]:
    """Return the chat messages for one summary."""
    rule = LENGTH_RULES.get(length, LENGTH_RULES[LENGTH_SHORT])
    user = (
        f"{rule} Put each paragraph in `summary` as a separate string, and up to 3 "
        "key facts in `key_facts`.\n\n"
        f"Headline: {title}\n\nArticle:\n{article}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def numbers_supported(summary: Summary, source_text: str) -> bool:
    """Return True if every number in the summary appears in the source text."""
    source_numbers = {n.replace(",", "") for n in _NUMBER.findall(source_text)}
    written = " ".join([*summary.paragraphs, *summary.key_facts])
    return all(n.replace(",", "") in source_numbers for n in _NUMBER.findall(written))


def parse_summary(content: str) -> Summary:
    """Parse and sanity-check the model's JSON reply."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError) as err:
        raise OllamaError("Model reply was not JSON") from err
    if not isinstance(data, dict):
        raise OllamaError("Model reply was not a JSON object")
    paragraphs = data.get("summary")
    facts = data.get("key_facts", [])
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    if not isinstance(paragraphs, list) or not isinstance(facts, list):
        raise OllamaError("Model reply had the wrong shape")
    paragraphs = [p.strip() for p in paragraphs if isinstance(p, str) and p.strip()]
    facts = [f.strip() for f in facts if isinstance(f, str) and f.strip()][:3]
    if not paragraphs:
        raise OllamaError("Model reply had no summary")
    return Summary(paragraphs=paragraphs, key_facts=facts)


class OllamaSummariser:
    """Write summaries with one Ollama model."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        model: str,
        length: str = LENGTH_SHORT,
    ) -> None:
        """Initialise the summariser."""
        self._session = session
        self._url = normalise_url(url)
        self.model = model
        self.length = length

    async def async_summarise(self, title: str, article: str) -> Summary:
        """Return a summary of the article."""
        body = {
            "model": self.model,
            "messages": build_messages(title, article, self.length),
            "stream": False,
            "think": False,
            "format": SUMMARY_SCHEMA,
            "options": {"temperature": 0.2},
        }
        try:
            async with self._session.post(
                f"{self._url}/api/chat",
                json=body,
                timeout=aiohttp.ClientTimeout(total=OLLAMA_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    raise OllamaError(f"Ollama replied {resp.status}")
                payload = await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise OllamaError(str(err)) from err
        try:
            content = payload["message"]["content"]
        except (KeyError, TypeError) as err:
            raise OllamaError("Unexpected reply from Ollama") from err
        return parse_summary(content)
