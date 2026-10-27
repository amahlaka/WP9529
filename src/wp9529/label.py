"""Render labels as print-ready images for a 12 mm (96-dot) print head.

Shared by the Home Assistant integration and the standalone CLI, so it must
not import anything from Home Assistant.

Layout, left to right along the label: [QR code] [MDI icon] [title / text].
Every part is optional; with no text, the QR code and icon are centred.
"""
import json
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

DOTS_PER_MM = 8
ASSETS = Path(__file__).with_name("assets")
MDI_FONT = ASSETS / "materialdesignicons-webfont.ttf"
MDI_CODEPOINTS = ASSETS / "mdi-codepoints.json"
FONT_CANDIDATES = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


@lru_cache(maxsize=1)
def _mdi_codepoints() -> dict[str, int]:
    return json.loads(MDI_CODEPOINTS.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def _mdi_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(MDI_FONT), size)


def mdi_glyph(icon: str) -> str:
    """Character for an MDI icon given as "mdi:tools" or "tools"."""
    name = icon.removeprefix("mdi:").strip()
    try:
        return chr(_mdi_codepoints()[name])
    except KeyError:
        raise ValueError(f"unknown MDI icon: {icon!r}") from None


def _fit_font(draw, text, max_w, max_h, start=48):
    size = start
    while size > 8:
        font = _font(size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= max_w and b - t <= max_h:
            return font
        size -= 1
    return _font(8)


def _line_height(font) -> int:
    l, t, r, b = font.getbbox("Ag")
    return b - t + 2


def _split_long_word(draw, word, font, max_w) -> list[str]:
    """Break a word wider than max_w into pieces that fit ("Korttisuoj", "at")."""
    pieces, piece = [], ""
    for ch in word:
        if piece and draw.textlength(piece + ch, font=font) > max_w:
            pieces.append(piece)
            piece = ch
        else:
            piece += ch
    return pieces + [piece] if piece else pieces


def _wrap(draw, text, font, max_w, break_words=False) -> list[str]:
    words = []
    for word in text.split():
        too_wide = break_words and draw.textlength(word, font=font) > max_w
        words += _split_long_word(draw, word, font, max_w) if too_wide else [word]
    lines, line = [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def _ellipsize(draw, text, font, max_w) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _fit_lines(draw, text, max_w, max_h, largest=22, smallest=12, max_lines=2):
    """Largest font (not below `smallest`) that fits `text` in at most `max_lines`
    lines; at the smallest size, overflow is cut with an ellipsis.

    Words are only broken when whole words cannot fit at any size, and then into
    as few lines as possible ("Korttisuo / jat", not "Kort / tisu / ojat").
    """
    attempts = [(False, max_lines)] + [(True, n) for n in range(1, max_lines + 1)]
    for break_words, n_lines in attempts:
        for size in range(largest, smallest - 1, -1):
            font = _font(size)
            lines = _wrap(draw, text, font, max_w, break_words)
            if (len(lines) <= n_lines and _line_height(font) * len(lines) <= max_h
                    and all(draw.textlength(ln, font=font) <= max_w for ln in lines)):
                return lines, font
    font = _font(smallest)
    n = max(1, min(max_lines, max_h // _line_height(font)))
    lines = _wrap(draw, text, font, max_w, break_words=True)
    head, rest = lines[:n - 1], " ".join(lines[n - 1:])
    return [_ellipsize(draw, ln, font, max_w) for ln in head] + [_ellipsize(draw, rest, font, max_w)], font


def qr_image(data: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, box_size=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("L")
    if img.width > size:
        raise ValueError(f"QR data too long for a 12 mm label ({len(data)} characters)")
    scale = max(1, size // img.width)  # integer scaling keeps modules crisp
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def icon_image(icon: str, size: int) -> Image.Image:
    glyph = mdi_glyph(icon)
    img = Image.new("L", (size, size), 255)
    ImageDraw.Draw(img).text((size / 2, size / 2), glyph, font=_mdi_font(size), fill=0, anchor="mm")
    return img


def render_label(title: str = "", text: str = "", qr: str | None = None, icon: str | None = None,
                 length_mm: float = 30, head_px: int = 96, margin_px: int = 4,
                 end_margin_mm: float = 1.5, rotate: int = 90) -> Image.Image:
    """Build a label image `head_px` wide and `length_mm` long, ready for print_image().

    `title` is drawn large, `text` below it (or on its own, up to 3 lines),
    `qr` is any string to encode, `icon` an MDI name like "mdi:tools".
    `end_margin_mm` keeps content off the label's rounded ends.
    """
    if not (title or text or qr or icon):
        raise ValueError("nothing to print: give a title, text, QR data or an icon")
    length_px = int(length_mm * DOTS_PER_MM)
    end_px = int(end_margin_mm * DOTS_PER_MM)
    box = head_px - 2 * margin_px
    canvas = Image.new("L", (length_px, head_px), 255)
    draw = ImageDraw.Draw(canvas)

    has_text = bool(title or text)
    blocks = []
    if qr:
        blocks.append(qr_image(qr, box))
    if icon:
        # Sharing the label with a QR code and text, a full-height icon would
        # leave almost no room for the text, so it shrinks to about 6 mm.
        icon_px = 6 * DOTS_PER_MM if (qr and has_text) else box
        blocks.append(icon_image(icon, icon_px))
    blocks_w = sum(b.width for b in blocks) + 2 * margin_px * max(0, len(blocks) - 1)

    x = end_px if has_text else max(end_px, (length_px - blocks_w) // 2)
    for b in blocks:
        canvas.paste(b, (x, (head_px - b.height) // 2))
        x += b.width + margin_px * 2

    text_w = length_px - x - end_px
    if has_text and text_w < 3 * DOTS_PER_MM:
        raise ValueError(f"no room for text on a {length_mm:g} mm label; drop the QR or the icon")

    if title and text:
        gap = 5
        title_font = _fit_font(draw, title, text_w, head_px * 0.42)
        tb = draw.textbbox((0, 0), title, font=title_font)
        title_h = tb[3] - tb[1]
        lines, text_font = _fit_lines(draw, text, text_w, box - title_h - gap)
        line_h = _line_height(text_font)
        y = (head_px - title_h - gap - line_h * len(lines)) // 2
        draw.text((x - tb[0], y - tb[1]), title, font=title_font, fill=0)
        y += title_h + gap
        for line in lines:
            draw.text((x, y), line, font=text_font, fill=0, anchor="lt")
            y += line_h
    elif title:
        font = _fit_font(draw, title, text_w, box, start=64)
        tb = draw.textbbox((0, 0), title, font=font)
        draw.text((x - tb[0], (head_px - (tb[3] - tb[1])) // 2 - tb[1]), title, font=font, fill=0)
    elif text:
        lines, font = _fit_lines(draw, text, text_w, box, largest=40, max_lines=3)
        line_h = _line_height(font)
        y = (head_px - line_h * len(lines)) // 2
        for line in lines:
            draw.text((x, y), line, font=font, fill=0, anchor="lt")
            y += line_h

    return canvas.rotate(rotate, expand=True)


def asset_tag(asset_id: str, name: str = "", url: str | None = None, icon: str | None = None,
              length_mm: float = 30, rotate: int = 90) -> Image.Image:
    """Homebox tag: QR link, optional icon, asset ID large with the item name below."""
    return render_label(title=asset_id, text=name, qr=url, icon=icon,
                        length_mm=length_mm, rotate=rotate)
