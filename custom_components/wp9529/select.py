"""Select: print darkness."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import WP9529ConfigEntry
from .entity import WP9529Entity
from .manager import PrinterManager
from .printer import DENSITY


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([DensitySelect(entry.runtime_data)])


class DensitySelect(WP9529Entity, SelectEntity, RestoreEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(DENSITY)
    _attr_icon = "mdi:brightness-6"

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "density")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in DENSITY:
            self.manager.density = last.state

    @property
    def current_option(self) -> str:
        return self.manager.density

    async def async_select_option(self, option: str) -> None:
        self.manager.density = option
        self.manager.async_update_listeners()
