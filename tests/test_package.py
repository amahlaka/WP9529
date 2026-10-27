"""CLI and renderer tests that don't need a printer."""
import pytest

from wp9529 import cli
from wp9529.label import render_label


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
