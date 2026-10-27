"""The pip package and the Home Assistant integration must render identical labels."""
import filecmp
from pathlib import Path

import pytest

from wp9529 import cli
from wp9529.label import render_label

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "src" / "wp9529"
COMPONENT = ROOT / "custom_components" / "wp9529"


def test_component_label_renderer_is_a_copy_of_the_package() -> None:
    """Edit src/wp9529/label.py (and assets/) and copy them into the integration."""
    assert (PACKAGE / "label.py").read_bytes() == (COMPONENT / "label.py").read_bytes()
    cmp = filecmp.dircmp(PACKAGE / "assets", COMPONENT / "assets")
    assert not (cmp.left_only or cmp.right_only or cmp.diff_files)


def test_cli_preview(tmp_path) -> None:
    cli.main(["--title", "Router", "--qr", "https://example.com", "--icon", "mdi:router-wireless",
              "--preview", str(tmp_path)])
    assert (tmp_path / "label.png").exists()


def test_cli_needs_something_to_do() -> None:
    with pytest.raises(SystemExit, match="nothing to do"):
        cli.main([])


def test_cli_rejects_bad_power_off() -> None:
    with pytest.raises(SystemExit):
        cli.main(["--power-off", "5"])


def test_render_label_size() -> None:
    assert render_label(title="000-042", text="Drill").size == (96, 240)
