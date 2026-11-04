"""Base entity for Briefly."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PROJECT_URL, VERSION
from .coordinator import BrieflyCoordinator


class BrieflyEntity(CoordinatorEntity[BrieflyCoordinator]):
    """An entity that belongs to a news desk device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BrieflyCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Briefly",
            model="News desk",
            sw_version=VERSION,
            configuration_url=PROJECT_URL,
            entry_type=DeviceEntryType.SERVICE,
        )
