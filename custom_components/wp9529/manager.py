"""State and print queue for one WP9529, shared by its entities and actions."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import io
import logging
from typing import Any

from PIL import Image, ImageOps

from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_DENSITY,
    DEFAULT_LABEL_GAP,
    DEFAULT_LABEL_LENGTH,
    DOMAIN,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_PRINTING,
)
from .label import render_label
from .printer import WP9529, PrinterError

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


@dataclass
class LabelContent:
    """What goes on a label; empty fields are left off."""

    title: str = ""
    text: str = ""
    qr: str = ""
    icon: str = ""

    def is_empty(self) -> bool:
        return not (self.title or self.text or self.qr or self.icon)


class PrinterManager:
    """Owns the Bluetooth presence, settings, UI form and print queue of one printer."""

    def __init__(self, hass: HomeAssistant, entry_id: str, address: str, name: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.address = address
        self.name = name
        self.lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{address}")

        self.present = False
        self.status = STATUS_IDLE
        self.last_error: str | None = None
        self.firmware: str | None = None
        self.charging: bool | None = None
        self.power_off_minutes: int | None = None  # as last read from the printer
        self.paper_problem: bool | None = None
        self.labels_printed = 0
        self.last_printed: datetime | None = None

        # Settings (config entities) and the UI print form (input entities).
        self.label_length = DEFAULT_LABEL_LENGTH
        self.label_gap = DEFAULT_LABEL_GAP
        self.density = DEFAULT_DENSITY
        self.form = LabelContent()
        self.form_copies = 1
        # Bumped whenever something that changes the label preview changes.
        self.preview_version = 0

    @callback
    def async_form_changed(self) -> None:
        self.preview_version += 1
        self.async_update_listeners()

    # --- listeners -----------------------------------------------------

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def async_update_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    @property
    def available(self) -> bool:
        # While printing the printer is connected to us and stops advertising.
        return self.present or self.status == STATUS_PRINTING

    # --- startup / presence ----------------------------------------------

    async def async_load(self) -> None:
        if data := await self._store.async_load():
            self.firmware = data.get("firmware")
            self.power_off_minutes = data.get("power_off_minutes")
            self.labels_printed = data.get("labels_printed", 0)
            if last := data.get("last_printed"):
                self.last_printed = dt_util.parse_datetime(last)

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Track whether the printer is advertising (on and not busy with the phone app)."""
        self.present = bluetooth.async_address_present(self.hass, self.address, connectable=True)

        @callback
        def _seen(service_info, change) -> None:
            if not self.present:
                self.present = True
                self.async_update_listeners()

        @callback
        def _gone(service_info) -> None:
            self.present = False
            self.async_update_listeners()

        unsubs = [
            bluetooth.async_register_callback(
                self.hass, _seen,
                bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.PASSIVE),
            bluetooth.async_track_unavailable(self.hass, _gone, self.address, connectable=True),
        ]

        @callback
        def _stop() -> None:
            for unsub in unsubs:
                unsub()

        return _stop

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(lambda: {
            "firmware": self.firmware,
            "power_off_minutes": self.power_off_minutes,
            "labels_printed": self.labels_printed,
            "last_printed": self.last_printed.isoformat() if self.last_printed else None,
        }, 5)

    # --- rendering ---------------------------------------------------------

    async def async_render(self, content: LabelContent, length_mm: float | None = None,
                           rotate: int = 90) -> Image.Image:
        """Render off the event loop; bad content raises ServiceValidationError."""
        if content.is_empty():
            raise ServiceValidationError("Nothing to print: fill in a title, text, QR code or icon")
        length = length_mm or self.label_length
        try:
            return await self.hass.async_add_executor_job(
                lambda: render_label(title=content.title, text=content.text, qr=content.qr or None,
                                     icon=content.icon or None, length_mm=length, rotate=rotate))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def async_preview_png(self) -> bytes:
        """The UI form as a landscape PNG, scaled up for screens."""
        def _png() -> bytes:
            try:
                img = render_label(title=self.form.title, text=self.form.text, qr=self.form.qr or None,
                                   icon=self.form.icon or None, length_mm=self.label_length, rotate=0)
            except ValueError:
                img = Image.new("L", (int(self.label_length * 8), 96), 255)
            img = ImageOps.expand(img.resize((img.width * 2, img.height * 2), Image.NEAREST),
                                  border=2, fill=160)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        return await self.hass.async_add_executor_job(_png)

    # --- printing ----------------------------------------------------------

    async def async_print(self, content: LabelContent, copies: int = 1, density: str | None = None,
                          length_mm: float | None = None) -> None:
        length = length_mm or self.label_length
        image = await self.async_render(content, length)
        await self._async_session(lambda printer: self._print_copies(printer, image, copies,
                                                                     density or self.density, length))

    async def async_print_form(self) -> None:
        await self.async_print(self.form, self.form_copies)

    async def async_set_power_off(self, minutes: int) -> None:
        """Store a new auto power-off time on the printer."""
        async def job(printer: WP9529) -> None:
            self.power_off_minutes = await printer.set_power_off_minutes(minutes)

        await self._async_session(job)

    async def async_refresh(self) -> None:
        """Connect briefly to read firmware, charging and error state."""
        await self._async_session(None)

    async def _print_copies(self, printer: WP9529, image: Image.Image, copies: int,
                            density: str, length: float) -> None:
        for _ in range(copies):
            await printer.print_image(image, density=density, label_mm=length, gap_mm=self.label_gap)
            self.labels_printed += 1
            self.last_printed = dt_util.utcnow()
            self.async_update_listeners()

    async def _async_session(self, job) -> None:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            raise HomeAssistantError(
                f"{self.name} is not reachable: it is off, out of Bluetooth range, "
                "or connected to the phone app")
        async with self.lock:
            self.status = STATUS_PRINTING
            self.async_update_listeners()
            try:
                async with WP9529(ble_device) as printer:
                    await self._read_state(printer)
                    if job is not None:
                        await job(printer)
                self.status = STATUS_IDLE
                self.last_error = None
            except PrinterError as err:
                self._fail(str(err))
                raise HomeAssistantError(f"Printing failed: {err}") from err
            except Exception as err:  # bleak raises a variety of connection errors
                _LOGGER.debug("printer connection failed", exc_info=True)
                self._fail(f"connection failed: {err}")
                if "ProfileUnavailable" in str(err) or "br-connection" in str(err):
                    raise HomeAssistantError(
                        "BlueZ tried to connect over classic Bluetooth instead of Bluetooth LE "
                        "and could not switch it to LE (needs BlueZ with experimental features, "
                        "as on Home Assistant OS). Using an ESPHome Bluetooth proxy avoids this. "
                        f"Details: {err}") from err
                raise HomeAssistantError(f"Could not talk to the printer: {err}") from err
            finally:
                self._save()
                self.async_update_listeners()

    def _fail(self, message: str) -> None:
        self.status = STATUS_ERROR
        self.last_error = message

    async def _read_state(self, printer: WP9529) -> None:
        self.paper_problem = printer.info.has_error if printer.info else None
        try:
            firmware = await printer.firmware_version()
            self.charging = (await printer.charging_state()) == 3
        except PrinterError:
            _LOGGER.debug("could not read firmware/charging state", exc_info=True)
            return
        try:
            self.power_off_minutes = await printer.power_off_minutes()
        except PrinterError:
            _LOGGER.debug("could not read the auto power-off time", exc_info=True)
        if firmware != self.firmware:
            self.firmware = firmware
            registry = dr.async_get(self.hass)
            identifier = (DOMAIN, self.address)
            # async_get_device_by_identifier replaced async_get_device in 2026.
            if lookup := getattr(registry, "async_get_device_by_identifier", None):
                device = lookup(identifier, self.entry_id)
            else:
                device = registry.async_get_device(identifiers={identifier})
            if device:
                registry.async_update_device(device.id, sw_version=firmware)
