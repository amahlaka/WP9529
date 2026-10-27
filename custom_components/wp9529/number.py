"""Numbers: copies for the form; label length and gap of the loaded roll; auto power-off."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WP9529ConfigEntry
from .entity import WP9529Entity
from .entity import WP9529LiveEntity
from .manager import PrinterManager
from .printer import POWER_OFF_MAX, POWER_OFF_MIN


@dataclass(frozen=True, kw_only=True)
class WP9529NumberDescription(NumberEntityDescription):
    attr: str  # PrinterManager attribute it controls
    cast: type = float


NUMBERS = [
    WP9529NumberDescription(
        key="copies", attr="form_copies", cast=int, icon="mdi:content-copy",
        native_min_value=1, native_max_value=20, native_step=1, mode=NumberMode.BOX),
    WP9529NumberDescription(
        key="label_length", attr="label_length", entity_category=EntityCategory.CONFIG,
        native_min_value=10, native_max_value=100, native_step=0.5, mode=NumberMode.BOX,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS, icon="mdi:arrow-expand-horizontal"),
    WP9529NumberDescription(
        key="label_gap", attr="label_gap", entity_category=EntityCategory.CONFIG,
        native_min_value=0, native_max_value=20, native_step=0.5, mode=NumberMode.BOX,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS, icon="mdi:arrow-split-vertical"),
]


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities([*(WP9529Number(manager, d) for d in NUMBERS), PowerOffNumber(manager)])


class WP9529Number(WP9529Entity, RestoreNumber):
    entity_description: WP9529NumberDescription

    def __init__(self, manager: PrinterManager, description: WP9529NumberDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._apply(last.native_value)

    @property
    def native_value(self) -> float:
        return getattr(self.manager, self.entity_description.attr)

    async def async_set_native_value(self, value: float) -> None:
        self._apply(value)

    def _apply(self, value: float) -> None:
        setattr(self.manager, self.entity_description.attr, self.entity_description.cast(value))
        self.manager.async_form_changed()


class PowerOffNumber(WP9529LiveEntity, NumberEntity):
    """The printer's own auto power-off time: read on every connection, written on change."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = POWER_OFF_MIN
    _attr_native_max_value = POWER_OFF_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-off-outline"

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "power_off")

    @property
    def native_value(self) -> int | None:
        return self.manager.power_off_minutes

    async def async_set_native_value(self, value: float) -> None:
        await self.manager.async_set_power_off(int(value))
