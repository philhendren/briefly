"""Button: refresh the desk now."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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
    """Set up the refresh button."""
    async_add_entities([BrieflyRefreshButton(entry.runtime_data.coordinator)])


class BrieflyRefreshButton(BrieflyEntity, ButtonEntity):
    """Press to fetch the feeds now."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: BrieflyCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        """Refresh now."""
        await self.coordinator.async_request_refresh()
