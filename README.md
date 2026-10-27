# WP9529 label printer

Print labels on a VSON **WP9529** Bluetooth label printer from a PC, without
the phone app: a Python package (`pip install wp9529-printer`) and a
command-line tool.

Labels can mix a QR code (URL, Wi-Fi details, any text), a large title, smaller
text and a [Material Design Icon](https://pictogrammers.com/library/mdi/).

The printer's Bluetooth protocol, reverse engineered from the iLabel app, is
documented in [PROTOCOL.md](PROTOCOL.md).

For Home Assistant, see [HA-WP9529](https://github.com/amahlaka/HA-WP9529), an
integration built on this package's label renderer. For Homebox asset tags,
see [Homebox-labeler](https://github.com/amahlaka/Homebox-labeler), which uses
this package.

## Requirements

- Windows, macOS or Linux with Bluetooth LE
- Python 3.12+
- A WP9529 with 30 × 12 mm die-cut labels (other sizes work with `--length`/`--gap`)

## Install

```bash
pip install wp9529-printer
```

This installs the `wp9529` module (`import wp9529`) and the `wp9529-label` command. To work on the code
instead, clone this repository and install it editable in a virtual
environment:

```bash
python -m venv .venv
```
```bash
.venv\Scripts\python -m pip install -e .
```

On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python`.

Turn the printer on and **close the phone app or disconnect it from the
printer**, because the printer only accepts one connection at a time. It
doesn't need pairing; the tool finds it automatically.

```bash
wp9529-label --info
```

```
printer 95:29:12:C2:09:0C: firmware V50
auto power-off after 96 minutes
```

## Printing labels

Any mix of `--title` (large text), `--text`, `--qr` and `--icon`:

```bash
wp9529-label --title Router --text "admin password in the vault" --icon mdi:router-wireless
```
```bash
wp9529-label --qr "WIFI:T:WPA;S:Home;P:secret;;" --text "Guest Wi-Fi"
```
```bash
wp9529-label --title Spices --preview previews
```

Layout, along the label: QR code, then icon, then text. With no text, the QR
code and icon are centred. On a 30 mm label, an icon next to both a QR code and
text shrinks to about 6 mm, and long text gets shortened with "…". Use
`--length 40` on longer labels for more room.

Your own image works too. It must be exactly 96 px wide (the print head); for a
30 mm label it should be 240 px tall, and the top prints first:

```bash
wp9529-label --image my_label.png
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--title TEXT` | | large text |
| `--text TEXT` | | smaller text, or the only text |
| `--qr DATA` | | any text to encode as a QR code |
| `--icon mdi:NAME` | | an MDI icon |
| `--image PATH` | | print an image 96 px wide |
| `--copies N` | 1 | copies of each label |
| `--length MM` | 30 | label length |
| `--gap MM` | 8.5 | gap between labels |
| `--continuous` | | continuous tape instead of die-cut labels |
| `--density` | normal | `light`, `normal` or `dark` |
| `--rotate` | 90 | use `270` if the text comes out upside down |
| `--feed N` | 0 | extra blank lines after each label |
| `--preview DIR` | | save PNGs to DIR instead of printing |
| `--address MAC` | scan | printer Bluetooth address (skips the scan) |
| `--info` | | show the firmware and auto power-off time |
| `--power-off MIN` | | set how many idle minutes before the printer switches itself off (10–180); the printer remembers it |
| `-v` | | verbose: log every Bluetooth packet |

`python -m wp9529` works the same as `wp9529-label`.

## Using it from Python

```python
import asyncio
from wp9529 import WP9529, asset_tag, render_label

async def main():
    img = render_label(title="Router", qr="https://example.com", icon="mdi:router-wireless")
    async with WP9529() as printer:  # scans for the printer; or WP9529("95:29:12:C2:09:0C")
        await printer.print_image(img, density="normal", label_mm=30, gap_mm=8.5)
        print(await printer.firmware_version(), await printer.power_off_minutes())

asyncio.run(main())
```

`asset_tag(asset_id, name, url, icon=...)` renders the ID + name + QR layout
used for inventory tags.

## Home Assistant

The Home Assistant integration lives in its own repository,
[HA-WP9529](https://github.com/amahlaka/HA-WP9529): sensors, settings, a print
form with live preview, a `notify` entity and the `wp9529.print_label` action.

## Development

The label renderer and its icon font live in `src/wp9529/label.py` and
`src/wp9529/assets/`. HA-WP9529 can't install this package inside Home
Assistant, so it carries an identical copy; after changing the renderer, copy
it there too. HA-WP9529's tests fail if the copies differ while both projects
sit side by side.

The tests cover the renderer and the CLI:

```bash
pip install -e . pytest
```
```bash
pytest
```

### Releasing

Releases go to [PyPI](https://pypi.org/project/wp9529-printer/) through the
[Publish workflow](.github/workflows/publish.yml), with trusted publishing (no
API tokens):

1. Bump `version` in `pyproject.toml` and push.
2. Optional: *Actions → Publish → Run workflow* uploads that build to
   [TestPyPI](https://test.pypi.org/project/wp9529-printer/); try it with
   `pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ wp9529-printer`.
   TestPyPI refuses a version it already has, so bump again to re-test.
3. Publish a GitHub release with the tag `v` + the version (e.g. `v0.1.1`).
   The workflow checks the tag matches, builds, smoke-tests the wheel and
   uploads it to PyPI.

## Troubleshooting

**"No WP9529 found"**: the printer is off, asleep, or connected to the phone
app (or Home Assistant). Turn it on, close the app and try again.

**Labels are shifted or run into the gap**: the printer has lost its place on
the roll. Use the printer's own re-align (feed) button, then print again. This
can happen after a job that is longer than the label. Don't change `--length`
or `--gap` to compensate.

**Text is upside down**: add `--rotate 270`.

**Print is too faint or too dark**: use `--density dark` or `--density light`.

**"unknown MDI icon"**: check the name at
[pictogrammers.com](https://pictogrammers.com/library/mdi/). The bundled font
is version 7.4.47, so icons added after it aren't available.

## Files

| Path | What it is |
|---|---|
| `src/wp9529/` | the Python package: `driver.py` (Bluetooth LE, `bleak`), `label.py` (renderer), `cli.py` (`wp9529-label`), `assets/` (MDI icon font 7.4.47, codepoints, license) |
| `tests/` | renderer and CLI tests |
| `tools/scan.py`, `tools/probe.py` | debugging helpers for finding the printer and sending raw commands |
| `PROTOCOL.md` | the reverse-engineered printer protocol |
| `.github/workflows/publish.yml` | build and publish to PyPI / TestPyPI |
| `LICENSE` | MIT; the bundled fonts keep their own licenses |
