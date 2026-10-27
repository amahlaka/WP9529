"""Image: live preview of the label form."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import WP9529ConfigEntry
from .entity import WP9529Entity
from .manager import PrinterManager


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([LabelPreview(hass, entry.runtime_data)])


class LabelPreview(WP9529Entity, ImageEntity):
    """What the Print button would print, drawn landscape at 2x."""

    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, manager: PrinterManager) -> None:
        WP9529Entity.__init__(self, manager, "preview")
        ImageEntity.__init__(self, hass)
        self._version = -1
        self._attr_image_last_updated = dt_util.utcnow()

    def _handle_manager_update(self) -> None:
        if self.manager.preview_version != self._version:
            self._version = self.manager.preview_version
            self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return await self.manager.async_preview_png()
