"""Binary sensors: in range, paper/cover problem, charging."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WP9529ConfigEntry
from .const import STATUS_ERROR
from .entity import WP9529Entity
from .manager import PrinterManager


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities([InRangeSensor(manager), ProblemSensor(manager), ChargingSensor(manager)])


class InRangeSensor(WP9529Entity, BinarySensorEntity):
    """On while the printer advertises: switched on and free for Home Assistant to use."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "in_range")

    @property
    def is_on(self) -> bool:
        return self.manager.available


class ProblemSensor(WP9529Entity, BinarySensorEntity):
    """Paper out, cover open or another error flag, as of the last connection."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "problem")

    @property
    def is_on(self) -> bool | None:
        if self.manager.paper_problem is None and self.manager.last_error is None:
            return None
        return bool(self.manager.paper_problem) or self.manager.status == STATUS_ERROR


class ChargingSensor(WP9529Entity, BinarySensorEntity):
    """Charging state, as of the last connection."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "charging")

    @property
    def is_on(self) -> bool | None:
        return self.manager.charging
