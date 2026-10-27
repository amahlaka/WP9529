"""Tests for forcing BlueZ to use Bluetooth LE (PreferredBearer)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from dbus_fast import MessageType

from custom_components.wp9529.bluez import async_prefer_le, bluez_device_path

PATH = "/org/bluez/hci0/dev_95_29_12_C2_09_0C"


def ble(details):
    return SimpleNamespace(address="95:29:12:C2:09:0C", name="9529#0952912C2090C", details=details)


def fake_bus(reply_type=MessageType.METHOD_RETURN):
    bus = MagicMock()
    bus.call = AsyncMock(return_value=SimpleNamespace(message_type=reply_type, error_name="x", body=[]))
    bus_cls = MagicMock()
    bus_cls.return_value.connect = AsyncMock(return_value=bus)
    return bus_cls, bus


def test_device_path() -> None:
    assert bluez_device_path(ble({"path": PATH, "props": {}})) == PATH
    assert bluez_device_path(ble({"source": "esphome-proxy-1"})) is None  # ESPHome proxy
    assert bluez_device_path(ble(None)) is None


async def test_sets_preferred_bearer_le() -> None:
    bus_cls, bus = fake_bus()
    with patch("dbus_fast.aio.MessageBus", bus_cls), patch("sys.platform", "linux"):
        assert await async_prefer_le(ble({"path": PATH})) is True
    msg = bus.call.await_args.args[0]
    assert (msg.destination, msg.path, msg.interface, msg.member) == (
        "org.bluez", PATH, "org.freedesktop.DBus.Properties", "Set")
    assert msg.body[0] == "org.bluez.Device1" and msg.body[1] == "PreferredBearer"
    assert msg.body[2].signature == "s" and msg.body[2].value == "le"
    bus.disconnect.assert_called_once()


async def test_bluez_refusal_is_not_fatal() -> None:
    bus_cls, bus = fake_bus(MessageType.ERROR)  # e.g. LE-only device: no such property
    with patch("dbus_fast.aio.MessageBus", bus_cls), patch("sys.platform", "linux"):
        assert await async_prefer_le(ble({"path": PATH})) is False
    bus.disconnect.assert_called_once()


async def test_no_dbus_is_not_fatal() -> None:
    bus_cls = MagicMock()
    bus_cls.return_value.connect = AsyncMock(side_effect=FileNotFoundError("no system bus"))
    with patch("dbus_fast.aio.MessageBus", bus_cls), patch("sys.platform", "linux"):
        assert await async_prefer_le(ble({"path": PATH})) is False


async def test_skipped_for_proxies_and_other_platforms() -> None:
    bus_cls, bus = fake_bus()
    with patch("dbus_fast.aio.MessageBus", bus_cls), patch("sys.platform", "linux"):
        assert await async_prefer_le(ble({"source": "esphome-proxy-1"})) is False
    with patch("dbus_fast.aio.MessageBus", bus_cls), patch("sys.platform", "win32"):
        assert await async_prefer_le(ble({"path": PATH})) is False
    bus.call.assert_not_called()
