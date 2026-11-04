"""Briefly: a Home Assistant news integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_SUMMARY_LENGTH,
    CONF_SUMMARY_MODE,
    DEFAULT_SUMMARY_LENGTH,
    DOMAIN,
    SUMMARY_OLLAMA,
)
from .coordinator import BrieflyCoordinator
from .http import BrieflyHttp
from .image_proxy import BrieflyImageView
from .ollama import OllamaSummariser
from .services import async_register_services
from .storage import BrieflyCache

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.EVENT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class BrieflyRuntime:
    """Objects that live as long as a loaded news desk."""

    coordinator: BrieflyCoordinator
    cache: BrieflyCache
    http: BrieflyHttp


type BrieflyConfigEntry = ConfigEntry[BrieflyRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the parts of Briefly shared by every news desk."""
    hass.http.register_view(BrieflyImageView(hass))
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BrieflyConfigEntry) -> bool:
    """Set up one news desk."""
    session = async_get_clientsession(hass)
    cache = BrieflyCache(hass, entry.entry_id)
    await cache.async_load()
    http = BrieflyHttp(session, cache)
    summariser = None
    if entry.options.get(CONF_SUMMARY_MODE) == SUMMARY_OLLAMA and entry.options.get(CONF_MODEL):
        summariser = OllamaSummariser(
            session,
            entry.options[CONF_OLLAMA_URL],
            entry.options[CONF_MODEL],
            entry.options.get(CONF_SUMMARY_LENGTH, DEFAULT_SUMMARY_LENGTH),
        )
    coordinator = BrieflyCoordinator(hass, entry, cache, http, summariser)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = BrieflyRuntime(coordinator, cache, http)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BrieflyConfigEntry) -> bool:
    """Unload a news desk, saving its cache."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.cache.async_save()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: BrieflyConfigEntry) -> None:
    """Delete the cache when a news desk is removed."""
    await BrieflyCache(hass, entry.entry_id).async_remove()
