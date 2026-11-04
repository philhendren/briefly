"""Sensors: one per section, plus last updated."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_SECTION_ID,
    CONF_SECTION_NAME,
    STATUS_DONE,
    STATUS_PENDING,
)
from .coordinator import BrieflyCoordinator
from .entity import BrieflyEntity
from .models import Section

if TYPE_CHECKING:
    from . import BrieflyConfigEntry

PARALLEL_UPDATES = 0
LAST_UPDATED_KEY = "last_updated"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrieflyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors and tidy away sensors for removed sections."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        BrieflySectionSensor(coordinator, section) for section in coordinator.section_config
    ]
    entities.append(BrieflyLastUpdatedSensor(coordinator))
    wanted = {entity.unique_id for entity in entities}
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain == "sensor" and reg_entry.unique_id not in wanted:
            registry.async_remove(reg_entry.entity_id)
    async_add_entities(entities)


class BrieflySectionSensor(BrieflyEntity, SensorEntity):
    """The stories in one section; the state is how many there are."""

    _attr_icon = "mdi:newspaper-variant-outline"
    _attr_native_unit_of_measurement = "stories"
    # Story lists can be large and change every refresh: keep them out of the recorder.
    _unrecorded_attributes = frozenset({"stories", "sources", "colour"})

    def __init__(self, coordinator: BrieflyCoordinator, section: dict[str, Any]) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, section[CONF_SECTION_ID])
        self.section_id: str = section[CONF_SECTION_ID]
        self._attr_name = section[CONF_SECTION_NAME]

    @property
    def _section(self) -> Section:
        # Sensors and sections are both built from the same options, and the
        # entry reloads whenever they change, so the section always exists.
        return self.coordinator.data.sections[self.section_id]

    @property
    def native_value(self) -> int:
        """Return the number of stories."""
        return len(self._section.stories)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the stories."""
        section = self._section
        return {
            "stories": [story.as_dict() for story in section.stories],
            "sources": section.sources,
            "colour": section.colour,
        }


class BrieflyLastUpdatedSensor(BrieflyEntity, SensorEntity):
    """When the desk last refreshed, with summary counts."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = LAST_UPDATED_KEY

    def __init__(self, coordinator: BrieflyCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, LAST_UPDATED_KEY)

    @property
    def native_value(self) -> datetime:
        """Return the time of the last refresh."""
        return self.coordinator.data.last_updated

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return summary counts and feed errors."""
        data = self.coordinator.data
        return {
            "summarised": data.count_status(STATUS_DONE),
            "pending": data.count_status(STATUS_PENDING),
            "errors": data.errors,
        }
