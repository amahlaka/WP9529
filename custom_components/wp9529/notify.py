"""Notify entity: notify.send_message prints the message as a label."""
from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WP9529ConfigEntry
from .entity import WP9529LiveEntity
from .manager import LabelContent, PrinterManager


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([LabelNotify(entry.runtime_data)])


class LabelNotify(WP9529LiveEntity, NotifyEntity):
    """Title becomes the large text, message the smaller text."""

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "label")

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        await self.manager.async_print(LabelContent(title=title or "", text=message))
