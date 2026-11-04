"""Spoken headlines through Alexa Media Player.

Alexa Media Player is a separate custom integration (installed from HACS),
not part of Briefly or of Home Assistant itself. Briefly only calls its
`notify.alexa_media` service when spoken headlines are switched on.
"""

from __future__ import annotations

import re

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import ALEXA_NOTIFY_SERVICE, DOMAIN
from .models import Story

_UNSAFE = re.compile(r"[<>{}\[\]\\]")


def speakable(text: str) -> str:
    """Return text that Alexa's text-to-speech reads cleanly."""
    text = text.replace("&", " and ")
    text = _UNSAFE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def build_headline_script(
    desk_name: str, stories: list[Story], section_name: str | None = None
) -> str:
    """Return the words Alexa will say."""
    where = f"{section_name} news" if section_name else desk_name
    if not stories:
        return speakable(f"There are no headlines from {where} right now.")
    count = len(stories)
    noun = "headline" if count == 1 else f"{count} headlines"
    intro = f"Here {'is the top' if count == 1 else 'are the top'} {noun} from {where}."
    lines = [intro]
    lines.extend(f"From {story.source}: {story.title.rstrip('.')}." for story in stories)
    return speakable(" ".join(lines))


def alexa_available(hass: HomeAssistant) -> bool:
    """Return True if Alexa Media Player's notify service exists."""
    return hass.services.has_service("notify", ALEXA_NOTIFY_SERVICE)


async def async_speak(hass: HomeAssistant, message: str, targets: list[str]) -> None:
    """Speak a message on Alexa devices through Alexa Media Player."""
    if not alexa_available(hass):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="alexa_media_missing"
        )
    await hass.services.async_call(
        "notify",
        ALEXA_NOTIFY_SERVICE,
        {"message": message, "target": targets, "data": {"type": "tts"}},
        blocking=True,
    )
