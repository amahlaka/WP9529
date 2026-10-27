"""Text inputs for the label form: title, text, QR content, icon."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import WP9529ConfigEntry
from .entity import WP9529Entity
from .label import mdi_glyph
from .manager import PrinterManager

FIELDS = {
    # key: (icon, mode)
    "title": ("mdi:format-title", TextMode.TEXT),
    "text": ("mdi:text", TextMode.TEXT),
    "qr": ("mdi:qrcode", TextMode.TEXT),
    "icon": ("mdi:emoticon-outline", TextMode.TEXT),
}


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities(FormText(manager, key, icon, mode) for key, (icon, mode) in FIELDS.items())


class FormText(WP9529Entity, TextEntity, RestoreEntity):
    """One field of the label form; empty means "leave it off the label"."""

    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(self, manager: PrinterManager, key: str, icon: str, mode: TextMode) -> None:
        super().__init__(manager, f"form_{key}")
        self._key = key
        self._attr_icon = icon
        self._attr_mode = mode

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in ("unknown", "unavailable"):
            setattr(self.manager.form, self._key, last.state)
            self.manager.async_form_changed()

    @property
    def native_value(self) -> str:
        return getattr(self.manager.form, self._key)

    async def async_set_value(self, value: str) -> None:
        value = value.strip()
        if self._key == "icon" and value:
            value = value if value.startswith("mdi:") else f"mdi:{value}"
            try:
                await self.hass.async_add_executor_job(mdi_glyph, value)
            except ValueError as err:
                raise ServiceValidationError(str(err)) from err
        setattr(self.manager.form, self._key, value)
        self.manager.async_form_changed()
