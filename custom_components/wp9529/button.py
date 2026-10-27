"""Buttons: print the UI form, refresh printer state."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WP9529ConfigEntry
from .entity import WP9529LiveEntity
from .manager import PrinterManager


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities([PrintButton(manager), RefreshButton(manager)])


class PrintButton(WP9529LiveEntity, ButtonEntity):
    """Print whatever is in the label form (title, text, QR code, icon, copies)."""

    _attr_icon = "mdi:printer"

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "print")

    async def async_press(self) -> None:
        await self.manager.async_print_form()


class RefreshButton(WP9529LiveEntity, ButtonEntity):
    """Connect briefly to update firmware, charging and problem state."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "refresh")

    async def async_press(self) -> None:
        await self.manager.async_refresh()
