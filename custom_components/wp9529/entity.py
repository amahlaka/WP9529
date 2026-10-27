"""Base entity for the WP9529."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL
from .manager import PrinterManager


class WP9529Entity(Entity):
    """Entity on the printer's device that redraws whenever the manager changes."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: PrinterManager, key: str) -> None:
        self.manager = manager
        self._attr_translation_key = key
        self._attr_unique_id = f"{manager.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.address)},
            connections={(CONNECTION_BLUETOOTH, manager.address)},
            name=manager.name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=manager.firmware,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.async_add_listener(self._handle_manager_update))

    def _handle_manager_update(self) -> None:
        self.async_write_ha_state()


class WP9529LiveEntity(WP9529Entity):
    """Reflects the printer itself, so it is unavailable when the printer is not around."""

    @property
    def available(self) -> bool:
        return self.manager.available
