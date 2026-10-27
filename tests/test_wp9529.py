"""Tests for the wp9529 printer integration (no Homebox involved)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.components.image import async_get_image
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import ADDRESS, NAME, printer_device

DOMAIN = "wp9529"


def eid(hass: HomeAssistant, platform: str, key: str) -> str:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}")


async def set_text(hass, key, value):
    await hass.services.async_call("text", "set_value", {"entity_id": eid(hass, "text", key), "value": value},
                                   blocking=True)


# --- config flow --------------------------------------------------------------

async def test_user_flow(hass: HomeAssistant, no_bluetooth_setup, fake_printer) -> None:
    info = SimpleNamespace(address=ADDRESS, name=NAME)
    with patch("custom_components.wp9529.config_flow.async_discovered_service_info", return_value=[info]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ADDRESS
    assert result["title"] == "WP9529 090C"


async def test_bluetooth_discovery_flow(hass: HomeAssistant, no_bluetooth_setup, fake_printer) -> None:
    info = SimpleNamespace(address=ADDRESS, name=NAME)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info)
    assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info)
    assert result["reason"] == "already_configured"


async def test_user_flow_nothing_found(hass: HomeAssistant) -> None:
    with patch("custom_components.wp9529.config_flow.async_discovered_service_info", return_value=[]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["reason"] == "no_devices_found"


# --- entities -------------------------------------------------------------------

async def test_entities_created(hass: HomeAssistant, printer_entry) -> None:
    expected = {
        "sensor": ["status", "labels_printed", "last_printed", "firmware"],
        "binary_sensor": ["in_range", "problem", "charging"],
        "button": ["print", "refresh"],
        "text": ["form_title", "form_text", "form_qr", "form_icon"],
        "number": ["copies", "label_length", "label_gap", "power_off"],
        "select": ["density"],
        "image": ["preview"],
        "notify": ["label"],
    }
    for platform, keys in expected.items():
        for key in keys:
            assert eid(hass, platform, key), f"{platform}.{key} missing"
    assert hass.states.get(eid(hass, "sensor", "status")).state == "idle"
    assert hass.states.get(eid(hass, "binary_sensor", "in_range")).state == "on"
    assert hass.states.get(eid(hass, "number", "label_length")).state == "30.0"
    assert hass.states.get(eid(hass, "select", "density")).state == "normal"


async def test_print_button_prints_form(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await set_text(hass, "form_title", "Router")
    await set_text(hass, "form_qr", "WIFI:T:WPA;S:Home;P:secret;;")
    await set_text(hass, "form_icon", "router-wireless")  # "mdi:" is added
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": eid(hass, "number", "copies"), "value": 2}, blocking=True)
    await hass.services.async_call("select", "select_option",
                                   {"entity_id": eid(hass, "select", "density"), "option": "dark"}, blocking=True)

    assert hass.states.get(eid(hass, "text", "form_icon")).state == "mdi:router-wireless"
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "print")}, blocking=True)

    assert len(fake_printer.jobs) == 2
    size, kwargs = fake_printer.jobs[0]
    assert size == (96, 240)
    assert kwargs == {"density": "dark", "label_mm": 30.0, "gap_mm": 8.5}
    assert hass.states.get(eid(hass, "sensor", "labels_printed")).state == "2"
    assert hass.states.get(eid(hass, "sensor", "firmware")).state == "V50"
    assert hass.states.get(eid(hass, "binary_sensor", "charging")).state == "on"
    assert hass.states.get(eid(hass, "binary_sensor", "problem")).state == "off"
    assert printer_device(hass, printer_entry).sw_version == "V50"


async def test_text_rejects_unknown_icon(hass: HomeAssistant, printer_entry) -> None:
    with pytest.raises(ServiceValidationError, match="unknown MDI icon"):
        await set_text(hass, "form_icon", "mdi:not-an-icon")


async def test_print_button_with_empty_form(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    with pytest.raises(ServiceValidationError, match="Nothing to print"):
        await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "print")},
                                       blocking=True)
    assert fake_printer.jobs == []


async def test_label_length_setting_used(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": eid(hass, "number", "label_length"), "value": 40}, blocking=True)
    await set_text(hass, "form_text", "Spare cables")
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "print")}, blocking=True)
    size, kwargs = fake_printer.jobs[0]
    assert size == (96, 320) and kwargs["label_mm"] == 40


async def test_preview_image(hass: HomeAssistant, printer_entry) -> None:
    before = hass.states.get(eid(hass, "image", "preview")).state
    await set_text(hass, "form_title", "Hello")
    image = await async_get_image(hass, eid(hass, "image", "preview"))
    assert image.content.startswith(b"\x89PNG")
    assert hass.states.get(eid(hass, "image", "preview")).state != before


async def test_notify_prints(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await hass.services.async_call("notify", "send_message",
                                   {"entity_id": eid(hass, "notify", "label"), "title": "Box 3",
                                    "message": "Winter clothes"}, blocking=True)
    assert len(fake_printer.jobs) == 1


async def test_refresh_button(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "refresh")},
                                   blocking=True)
    assert fake_printer.jobs == []
    assert hass.states.get(eid(hass, "sensor", "firmware")).state == "V50"


async def test_classic_bluetooth_error_explained(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    fake_printer.fail_with = Exception(
        "Failed to connect after 3 attempt(s): [org.bluez.Error.BREDR.ProfileUnavailable] "
        "No more profiles to connect to")
    with pytest.raises(HomeAssistantError, match="classic Bluetooth instead of Bluetooth LE"):
        await hass.services.async_call(DOMAIN, "print_label", {"title": "x"}, blocking=True)


async def test_connection_failure_sets_error(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    fake_printer.fail_with = OSError("boom")
    with pytest.raises(HomeAssistantError, match="Could not talk to the printer"):
        await hass.services.async_call("notify", "send_message",
                                       {"entity_id": eid(hass, "notify", "label"), "message": "x"}, blocking=True)
    status = hass.states.get(eid(hass, "sensor", "status"))
    assert status.state == "error"
    assert "boom" in status.attributes["last_error"]
    assert hass.states.get(eid(hass, "binary_sensor", "problem")).state == "on"


async def test_power_off_read_and_set(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    power_off = eid(hass, "number", "power_off")
    assert hass.states.get(power_off).state == "unknown"  # not connected yet
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "refresh")},
                                   blocking=True)
    assert hass.states.get(power_off).state == "96"

    await hass.services.async_call("number", "set_value", {"entity_id": power_off, "value": 30}, blocking=True)
    assert fake_printer.power_off == 30
    assert hass.states.get(power_off).state == "30"
    assert fake_printer.jobs == []

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("number", "set_value", {"entity_id": power_off, "value": 5}, blocking=True)
    assert fake_printer.power_off == 30


async def test_power_off_unsupported(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    fake_printer.power_off = None  # printer doesn't answer b4
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "refresh")},
                                   blocking=True)
    assert hass.states.get(eid(hass, "number", "power_off")).state == "unknown"
    assert hass.states.get(eid(hass, "sensor", "firmware")).state == "V50"


# --- action ---------------------------------------------------------------------

async def test_print_label_action(hass: HomeAssistant, printer_device_id, fake_printer) -> None:
    await hass.services.async_call(DOMAIN, "print_label", {
        "device_id": printer_device_id, "qr": "https://example.com", "text": "Example",
        "icon": "mdi:link", "density": "light", "label_length": 40, "copies": 3}, blocking=True)
    assert len(fake_printer.jobs) == 3
    size, kwargs = fake_printer.jobs[0]
    assert size == (96, 320) and kwargs["density"] == "light"


async def test_print_label_action_empty_fields_ignored(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await hass.services.async_call(DOMAIN, "print_label", {"title": "Only a title", "icon": "", "qr": ""},
                                   blocking=True)
    assert len(fake_printer.jobs) == 1


async def test_print_label_action_unreachable(hass: HomeAssistant, printer_entry) -> None:
    with patch("custom_components.wp9529.manager.bluetooth.async_ble_device_from_address", return_value=None):
        with pytest.raises(HomeAssistantError, match="not reachable"):
            await hass.services.async_call(DOMAIN, "print_label", {"title": "x"}, blocking=True)


async def test_print_label_action_wrong_device(hass: HomeAssistant, printer_entry) -> None:
    with pytest.raises(ServiceValidationError, match="Unknown device"):
        await hass.services.async_call(DOMAIN, "print_label", {"device_id": "nope", "title": "x"}, blocking=True)
