"""Tests for fitting text onto the label."""
from PIL import Image, ImageDraw

from wp9529.label import _fit_lines, render_label


def draw():
    return ImageDraw.Draw(Image.new("L", (10, 10)))


def test_long_word_breaks_into_fewest_lines() -> None:
    # Too long for one line even at the smallest size, whichever system font
    # the renderer finds (Arial Bold on Windows, DejaVu Sans Bold on Linux).
    word = "Korttisuojapakkaukset"
    lines, _ = _fit_lines(draw(), word, max_w=77, max_h=88, largest=40, max_lines=3)
    assert 2 <= len(lines) <= 3 and "".join(lines) == word


def test_whole_words_preferred_over_breaking() -> None:
    lines, _ = _fit_lines(draw(), "Dungeon Crawler Carl", max_w=77, max_h=88, largest=40, max_lines=3)
    assert lines == ["Dungeon", "Crawler", "Carl"]


def test_qr_name_icon_layout_renders() -> None:
    img = render_label(text="Korttisuojat", qr="https://x/a/000-010", icon="mdi:cards-playing-outline")
    assert img.size == (96, 240)
