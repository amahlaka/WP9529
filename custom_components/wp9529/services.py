"""The wp9529.print_label action, for scripts, automations and other integrations."""
from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ATTR_COPIES,
    ATTR_DENSITY,
    ATTR_DEVICE_ID,
    ATTR_ICON,
    ATTR_LABEL_LENGTH,
    ATTR_QR,
    ATTR_TEXT,
    ATTR_TITLE,
    DOMAIN,
    SERVICE_PRINT_LABEL,
)
from .manager import LabelContent
from .printer import DENSITY

if TYPE_CHECKING:
    from .manager import PrinterManager

PRINT_LABEL_SCHEMA = vol.Schema({
    vol.Optional(ATTR_DEVICE_ID): cv.string,
    vol.Optional(ATTR_TITLE, default=""): vol.Any(None, cv.string),
    vol.Optional(ATTR_TEXT, default=""): vol.Any(None, cv.string),
    vol.Optional(ATTR_QR, default=""): vol.Any(None, cv.string),
    # Empty values count as "not set", so scripts can pass optional fields through.
    vol.Optional(ATTR_ICON, default=""): vol.Any(None, "", cv.icon),
    vol.Optional(ATTR_COPIES, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
    vol.Optional(ATTR_DENSITY): vol.In(list(DENSITY)),
    vol.Optional(ATTR_LABEL_LENGTH): vol.All(vol.Coerce(float), vol.Range(min=10, max=100)),
})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def print_label(call: ServiceCall) -> None:
        manager = async_get_manager(hass, call.data.get(ATTR_DEVICE_ID))
        content = LabelContent(title=call.data[ATTR_TITLE] or "", text=call.data[ATTR_TEXT] or "",
                               qr=call.data[ATTR_QR] or "", icon=call.data[ATTR_ICON] or "")
        await manager.async_print(content, copies=call.data[ATTR_COPIES],
                                  density=call.data.get(ATTR_DENSITY),
                                  length_mm=call.data.get(ATTR_LABEL_LENGTH))

    hass.services.async_register(DOMAIN, SERVICE_PRINT_LABEL, print_label, schema=PRINT_LABEL_SCHEMA)


@callback
def async_get_manager(hass: HomeAssistant, device_id: str | None) -> PrinterManager:
    """The printer for a device ID, or the only printer when none is given."""
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise ServiceValidationError(f"Unknown device {device_id}")
        entries = [e for e in entries if e.entry_id in device.config_entries]
    if not entries:
        raise ServiceValidationError("No WP9529 printer is set up" if not device_id
                                     else "That device is not a loaded WP9529 printer")
    if len(entries) > 1:
        raise ServiceValidationError("Several printers are set up; pass device_id")
    return entries[0].runtime_data
