"""Briefly services."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_COUNT,
    ATTR_SECTION,
    ATTR_STORY_ID,
    ATTR_TARGETS,
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_TARGETS,
    DOMAIN,
    SERVICE_GET_STORIES,
    SERVICE_REFRESH,
    SERVICE_SPEAK_HEADLINES,
    SERVICE_SUMMARISE,
    STATUS_DONE,
)
from .models import Section, Story
from .speech import async_speak, build_headline_script

if TYPE_CHECKING:
    from . import BrieflyConfigEntry

ENTRY_SCHEMA = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}

REFRESH_SCHEMA = vol.Schema(ENTRY_SCHEMA)
GET_STORIES_SCHEMA = vol.Schema(
    {
        **ENTRY_SCHEMA,
        vol.Optional(ATTR_SECTION): cv.string,
        vol.Optional(ATTR_COUNT, default=5): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=25)
        ),
    }
)
SUMMARISE_SCHEMA = vol.Schema({vol.Required(ATTR_STORY_ID): cv.string})
SPEAK_SCHEMA = vol.Schema(
    {
        **ENTRY_SCHEMA,
        vol.Optional(ATTR_SECTION): cv.string,
        vol.Optional(ATTR_COUNT, default=3): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=10)
        ),
        vol.Optional(ATTR_TARGETS): cv.entity_ids,
    }
)


def _entries(hass: HomeAssistant, entry_id: str | None) -> list[BrieflyConfigEntry]:
    if entry_id is None:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_desks"
            )
        return entries
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="desk_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    return [entry]


def _matches(section: Section, wanted: str) -> bool:
    return wanted.casefold() in (section.id.casefold(), section.name.casefold())


def _select(
    entries: list[BrieflyConfigEntry], section: str | None, count: int
) -> tuple[list[tuple[Section, Story]], Section | None]:
    """Return up to `count` stories, round-robin across sections."""
    columns: list[tuple[Section, list[Story]]] = []
    matched: Section | None = None
    for entry in entries:
        data = entry.runtime_data.coordinator.data
        for sec in data.sections.values() if data else []:
            if section is None or _matches(sec, section):
                columns.append((sec, sec.stories))
                matched = matched or sec
    if section is not None and matched is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="section_not_found",
            translation_placeholders={"section": section},
        )
    picked: list[tuple[Section, Story]] = []
    ids: set[str] = set()
    for rank in range(max((len(s) for _c, s in columns), default=0)):
        for sec, stories in columns:
            if rank < len(stories) and stories[rank].id not in ids and len(picked) < count:
                ids.add(stories[rank].id)
                picked.append((sec, stories[rank]))
    return picked, matched if section is not None else None


async def _refresh(call: ServiceCall) -> None:
    for entry in _entries(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID)):
        await entry.runtime_data.coordinator.async_request_refresh()


async def _get_stories(call: ServiceCall) -> ServiceResponse:
    entries = _entries(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    picked, _section = _select(entries, call.data.get(ATTR_SECTION), call.data[ATTR_COUNT])
    return {
        "stories": [
            {**story.as_dict(), "section": sec.name, "colour": sec.colour}
            for sec, story in picked
        ]
    }


async def _summarise(call: ServiceCall) -> ServiceResponse:
    story_id = call.data[ATTR_STORY_ID]
    for entry in _entries(call.hass, None):
        coordinator = entry.runtime_data.coordinator
        story = coordinator.data.find_story(story_id) if coordinator.data else None
        if story is None:
            continue
        if not coordinator.summaries_enabled:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="summaries_off"
            )
        if story.summary_status != STATUS_DONE:
            await coordinator.async_summarise_story(story)
            coordinator.cache.schedule_save()
            coordinator.refresh_statuses()
        refreshed = coordinator.data.find_story(story_id) or story
        return {"story": refreshed.as_dict()}
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="story_not_found",
        translation_placeholders={"story_id": story_id},
    )


async def _speak_headlines(call: ServiceCall) -> None:
    entries = _entries(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    entry = entries[0]
    if not entry.options.get(CONF_ALEXA_ENABLED):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="alexa_disabled",
            translation_placeholders={"desk": entry.title},
        )
    targets: list[str] = call.data.get(ATTR_TARGETS) or entry.options.get(
        CONF_ALEXA_TARGETS, []
    )
    if not targets:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="alexa_no_targets"
        )
    picked, section = _select([entry], call.data.get(ATTR_SECTION), call.data[ATTR_COUNT])
    message = build_headline_script(
        entry.title, [story for _s, story in picked], section.name if section else None
    )
    await async_speak(call.hass, message, targets)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register Briefly's services."""
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh, REFRESH_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_STORIES,
        _get_stories,
        GET_STORIES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SUMMARISE,
        _summarise,
        SUMMARISE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SPEAK_HEADLINES, _speak_headlines, SPEAK_SCHEMA
    )

