"""Run the example script from examples/homeassistant/scripts.yaml for real."""
from pathlib import Path

import pytest
import yaml

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

SCRIPTS = Path(__file__).parent.parent / "examples" / "homeassistant" / "scripts.yaml"


@pytest.fixture
async def scripts(hass: HomeAssistant, printer_entry):
    config = yaml.safe_load(SCRIPTS.read_text(encoding="utf-8"))
    assert await async_setup_component(hass, "script", {"script": config})
    await hass.async_block_till_done()


async def test_print_free_label_script(hass: HomeAssistant, scripts, fake_printer) -> None:
    await hass.services.async_call("script", "print_free_label",
                                   {"qr": "https://example.com", "icon": "mdi:link", "copies": 2}, blocking=True)
    assert len(fake_printer.jobs) == 2
