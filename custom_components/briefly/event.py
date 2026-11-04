"""Event entity: fires once for every new story."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EVENT_NEW_STORY
from .coordinator import BrieflyCoordinator
from .entity import BrieflyEntity

if TYPE_CHECKING:
    from . import BrieflyConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrieflyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the new story event entity."""
    async_add_entities([BrieflyNewStoryEvent(entry.runtime_data.coordinator)])


class BrieflyNewStoryEvent(BrieflyEntity, EventEntity):
    """Fires `new_story` when a story first appears in any section."""

    _attr_event_types = [EVENT_NEW_STORY]
    _attr_translation_key = EVENT_NEW_STORY

    def __init__(self, coordinator: BrieflyCoordinator) -> None:
        """Initialise the event entity."""
        super().__init__(coordinator, EVENT_NEW_STORY)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        for section_id, story in data.new_stories:
            section = data.sections[section_id]
            self._trigger_event(
                EVENT_NEW_STORY,
                {
                    "story_id": story.id,
                    "section": section.name,
                    "title": story.title,
                    "source": story.source,
                    "link": story.link,
                },
            )
            self.async_write_ha_state()
