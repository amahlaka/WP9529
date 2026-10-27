"""VSON WP9529 Bluetooth label printer."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .manager import PrinterManager
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.TEXT,
]

type WP9529ConfigEntry = ConfigEntry[PrinterManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry) -> bool:
    # The printer is only connected while a job runs, so setup never fails just
    # because it is switched off; its entities show it as unavailable instead.
    manager = PrinterManager(hass, entry.entry_id, entry.unique_id, entry.title)
    await manager.async_load()
    entry.runtime_data = manager
    entry.async_on_unload(manager.async_start())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WP9529ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
