"""Make BlueZ connect to the printer over Bluetooth LE, not classic BR/EDR.

The WP9529 advertises the "BR/EDR supported" flag, so BlueZ treats it as a
dual-mode device. BlueZ then updates the last-seen time of both bearers from
each advertisement, and breaks the tie in favour of BR/EDR, where the printer
offers nothing: Connect() fails with org.bluez.Error.BREDR.ProfileUnavailable.

BlueZ's fix is the Device1.PreferredBearer property. It is experimental, but
Home Assistant OS runs bluetoothd with --experimental (passive scanning needs
it). The property only exists for dual-mode devices and only on BlueZ, so this
is a no-op for ESPHome Bluetooth proxies, other OSes and LE-only devices.
"""
from __future__ import annotations

import logging
import sys

from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

BLUEZ = "org.bluez"
DEVICE_INTERFACE = "org.bluez.Device1"


def bluez_device_path(ble_device: BLEDevice) -> str | None:
    """D-Bus object path of a device seen by a local BlueZ adapter, else None."""
    details = ble_device.details
    if isinstance(details, dict) and isinstance(path := details.get("path"), str):
        return path if path.startswith("/org/bluez/") else None
    return None


async def async_prefer_le(ble_device: BLEDevice) -> bool:
    """Set PreferredBearer=le on BlueZ; True if it was set. Never raises."""
    if sys.platform != "linux" or not (path := bluez_device_path(ble_device)):
        return False
    try:
        from dbus_fast import BusType, Message, MessageType, Variant
        from dbus_fast.aio import MessageBus
    except ImportError:
        return False
    try:
        from bleak.backends.bluezdbus.utils import get_dbus_authenticator
        auth = get_dbus_authenticator()
    except ImportError:
        auth = None

    bus = None
    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM, auth=auth).connect()
        reply = await bus.call(Message(
            destination=BLUEZ, path=path, interface="org.freedesktop.DBus.Properties",
            member="Set", signature="ssv",
            body=[DEVICE_INTERFACE, "PreferredBearer", Variant("s", "le")]))
        if reply.message_type == MessageType.ERROR:
            # LE-only device, BlueZ too old, or bluetoothd without --experimental.
            _LOGGER.debug("PreferredBearer not set on %s: %s %s", path, reply.error_name, reply.body)
            return False
        _LOGGER.debug("PreferredBearer=le set on %s", path)
        return True
    except Exception:  # D-Bus unavailable (e.g. container without the system bus)
        _LOGGER.debug("could not set PreferredBearer on %s", path, exc_info=True)
        return False
    finally:
        if bus is not None:
            bus.disconnect()
