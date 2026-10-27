"""Sensors: status, firmware, labels printed, last printed."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WP9529ConfigEntry
from .const import STATUS_ERROR, STATUS_IDLE, STATUS_PRINTING
from .entity import WP9529Entity, WP9529LiveEntity
from .manager import PrinterManager


@dataclass(frozen=True, kw_only=True)
class WP9529SensorDescription(SensorEntityDescription):
    value: Callable[[PrinterManager], Any]
    live: bool = False


SENSORS = [
    WP9529SensorDescription(
        key="status", device_class=SensorDeviceClass.ENUM,
        options=[STATUS_IDLE, STATUS_PRINTING, STATUS_ERROR],
        value=lambda m: m.status, live=True),
    WP9529SensorDescription(
        key="labels_printed", state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="labels", value=lambda m: m.labels_printed),
    WP9529SensorDescription(
        key="last_printed", device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda m: m.last_printed),
    WP9529SensorDescription(
        key="firmware", entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda m: m.firmware),
]


async def async_setup_entry(hass: HomeAssistant, entry: WP9529ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities(
        (WP9529LiveSensor if d.live else WP9529Sensor)(manager, d) for d in SENSORS)


class WP9529Sensor(WP9529Entity, SensorEntity):
    entity_description: WP9529SensorDescription

    def __init__(self, manager: PrinterManager, description: WP9529SensorDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.manager)


class WP9529LiveSensor(WP9529LiveEntity, WP9529Sensor):
    """Status: unavailable while the printer is off or held by the phone app."""

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return {"last_error": self.manager.last_error} if self.manager.last_error else None
