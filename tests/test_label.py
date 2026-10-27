"""Tests for fitting text onto the label."""
from PIL import Image, ImageDraw

from custom_components.wp9529.label import _fit_lines, render_label


def draw():
    return ImageDraw.Draw(Image.new("L", (10, 10)))


def test_long_word_breaks_into_fewest_lines() -> None:
    lines, _ = _fit_lines(draw(), "Korttisuojat", max_w=77, max_h=88, largest=40, max_lines=3)
    assert len(lines) == 2 and "".join(lines) == "Korttisuojat"


def test_whole_words_preferred_over_breaking() -> None:
    lines, _ = _fit_lines(draw(), "Dungeon Crawler Carl", max_w=77, max_h=88, largest=40, max_lines=3)
    assert lines == ["Dungeon", "Crawler", "Carl"]


def test_qr_name_icon_layout_renders() -> None:
    img = render_label(text="Korttisuojat", qr="https://x/a/000-010", icon="mdi:cards-playing-outline")
    assert img.size == (96, 240)
