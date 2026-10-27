"""Shared fixtures: a fake printer and fake Bluetooth for the wp9529 integration."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.wp9529.printer import Info, PrinterError

pytest_plugins = "pytest_homeassistant_custom_component"

ADDRESS = "95:29:12:C2:09:0C"
NAME = "9529#0952912C2090C"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load integrations from custom_components/."""
    yield


class FakePrinter:
    """Stands in for printer.WP9529 and records what would be printed."""

    jobs: list = []
    fail_with: Exception | None = None

    def __init__(self, ble_device):
        self.info = Info(bytes.fromhex("010c0060000000000000015301"))

    async def __aenter__(self):
        if FakePrinter.fail_with:
            raise FakePrinter.fail_with
        return self

    async def __aexit__(self, *exc):
        return None

    async def firmware_version(self):
        return "V50"

    async def charging_state(self):
        return 3

    power_off = 96  # minutes, as read from the real printer (b4 60 ..)

    async def power_off_minutes(self):
        if FakePrinter.power_off is None:
            raise PrinterError("no reply to b4")
        return FakePrinter.power_off

    async def set_power_off_minutes(self, minutes):
        FakePrinter.power_off = minutes
        return minutes

    async def print_image(self, img, **kwargs):
        FakePrinter.jobs.append((img.size, kwargs))


@pytest.fixture
def fake_printer():
    """Fake Bluetooth (printer present) and a fake printer driver."""
    FakePrinter.jobs = []
    FakePrinter.fail_with = None
    FakePrinter.power_off = 96
    bt = "custom_components.wp9529.manager.bluetooth"
    with (
        patch("custom_components.wp9529.manager.WP9529", FakePrinter),
        patch(f"{bt}.async_address_present", return_value=True),
        patch(f"{bt}.async_register_callback", return_value=lambda: None),
        patch(f"{bt}.async_track_unavailable", return_value=lambda: None),
        patch(f"{bt}.async_ble_device_from_address", return_value=SimpleNamespace(address=ADDRESS, name=NAME)),
    ):
        yield FakePrinter


@pytest.fixture
def no_bluetooth_setup(hass: HomeAssistant):
    """Pretend the bluetooth_adapters dependency is already set up."""
    hass.config.components.add("bluetooth_adapters")


@pytest.fixture
async def printer_entry(hass: HomeAssistant, no_bluetooth_setup, fake_printer) -> MockConfigEntry:
    entry = MockConfigEntry(domain="wp9529", unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}, title=NAME)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def printer_device(hass: HomeAssistant, entry) -> dr.DeviceEntry:
    return dr.async_get(hass).async_get_device_by_identifier(("wp9529", ADDRESS), entry.entry_id)


@pytest.fixture
def printer_device_id(hass: HomeAssistant, printer_entry) -> str:
    return printer_device(hass, printer_entry).id
