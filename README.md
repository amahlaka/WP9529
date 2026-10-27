# WP9529 label printer

Print labels on a VSON **WP9529** Bluetooth label printer without the phone
app: from a PC with a Python package and command-line tool, or from Home
Assistant with a custom integration.

Labels can mix a QR code (URL, Wi-Fi details, any text), a large title, smaller
text and a [Material Design Icon](https://pictogrammers.com/library/mdi/).

The printer's Bluetooth protocol, reverse engineered from the iLabel app, is
documented in [PROTOCOL.md](PROTOCOL.md).

For Homebox asset tags, see the **Homebox-labeler** project, which builds on
this package and integration.

## Requirements

- Windows, macOS or Linux with Bluetooth LE
- Python 3.12+
- A WP9529 with 30 × 12 mm die-cut labels (other sizes work with `--length`/`--gap`)

## Install

```bash
python -m venv .venv
```
```bash
.venv\Scripts\python -m pip install -e .
```

On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python`. This
installs the `wp9529` package and the `wp9529-label` command.

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

`custom_components/wp9529` is a Home Assistant integration for the printer:
sensors, settings, a print form with live preview in the UI, a `notify` entity
and the `wp9529.print_label` action for scripts and other integrations.

The printer is reached through Home Assistant's own Bluetooth: an adapter on
the Home Assistant machine, or an
[ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
near the printer. Tested with Home Assistant 2026.10.

### Install

1. Copy `custom_components/wp9529` into `/config/custom_components/` on Home
   Assistant (Samba, SSH or Studio Code Server add-on). Restart Home Assistant.
2. Turn the printer on and close the phone app. Under *Settings → Devices &
   services* a **VSON WP9529 Label Printer** appears as discovered: click
   **Add**. If not, *Add integration* → search "WP9529".

### Printer device

| Entity | Kind | Purpose |
|---|---|---|
| Label title / Label text / Label QR code / Label icon | text | the print form; empty fields are left off the label. The icon is checked against the bundled MDI set (`mdi:` is added if you leave it out) |
| Copies | number | copies for the Print button |
| Label preview | image | live preview of the form |
| Print label | button | prints the form |
| Status | sensor | `idle` / `printing` / `error` (with a `last_error` attribute); unavailable while the printer is off or held by the phone app |
| Labels printed, Last printed | sensor | counter and timestamp, kept across restarts |
| Problem | binary sensor | paper/cover error, or the last job failed |
| Charging | binary sensor | charging state, as of the last connection |
| In range | binary sensor (diagnostic) | the printer is advertising and free to connect |
| Firmware | sensor (diagnostic) | e.g. V50; also shown on the device |
| Refresh status | button (diagnostic) | connect briefly to update firmware, charging and problem |
| Label length, Label gap | number (config) | the loaded roll: 30 mm / 8.5 mm |
| Print darkness | select (config) | light / normal / dark |
| Auto power-off | number (config) | minutes of inactivity before the printer switches itself off (10–180). Stored on the printer: read on every connection, and changing it connects to write it |
| Label | notify | `notify.send_message` prints title (large) and message |

The printer is only connected while printing or refreshing, so it can sleep in
between and the phone app keeps working. Firmware, charging and problem update
whenever Home Assistant connects.

### Action

**`wp9529.print_label`**: the printer's public action, for scripts,
automations and other integrations.

| Field | Meaning |
|---|---|
| `device_id` | which printer; optional with only one |
| `title` | large text |
| `text` | smaller text, or the only text |
| `qr` | any text to encode: URL, `WIFI:T:WPA;S:name;P:pass;;`, etc. |
| `icon` | MDI icon, e.g. `mdi:tools` |
| `copies` | 1–50 |
| `density`, `label_length` | override the printer's settings for this job |

Any mix works: QR only, icon only, text only, title + text + QR + icon, and so
on. Empty values (`""`) count as not set, so scripts can pass optional fields
straight through.

```yaml
action: wp9529.print_label
data:
  title: Guest Wi-Fi
  qr: "WIFI:T:WPA;S:Home;P:secret;;"
  icon: mdi:wifi
```

Plain text from anything that can send a notification:

```yaml
action: notify.send_message
target:
  entity_id: notify.wp9529_090c_label
data:
  title: Box 3
  message: Winter clothes
```

### Examples

Ready-made YAML is in [examples/homeassistant](examples/homeassistant). Entity
IDs assume the printer is named "WP9529 090C":

- [`scripts.yaml`](examples/homeassistant/scripts.yaml): `script.print_free_label`
  with title, text, QR content, icon and copies
- [`automations.yaml`](examples/homeassistant/automations.yaml): a guest Wi-Fi
  label from a button helper or NFC tag, and a notification when the printer
  reports a problem
- [`dashboard-card.yaml`](examples/homeassistant/dashboard-card.yaml): a print
  form with preview, the fields, status and a Print button

## Development

The label renderer and its icon font live in `src/wp9529/label.py` and
`src/wp9529/assets/`. The Home Assistant integration can't install this
package, so it carries an identical copy in `custom_components/wp9529/`; after
changing the renderer, copy it there too. A test fails if the two differ.

The tests cover the integration (config flow, every entity, the action,
`notify`, preview, errors), the BlueZ workaround, the renderer and the CLI.
They need Linux (or WSL) with Python 3.14:

```bash
pip install -e . pytest-homeassistant-custom-component
```
```bash
pytest
```

Home Assistant's Bluetooth component also needs its own requirements: install
those listed in the `manifest.json` of the `bluetooth`, `bluetooth_adapters`,
`usb` and `hassio` components.

## Troubleshooting

**"No WP9529 found"**: the printer is off, asleep, or connected to the phone
app. Turn it on, close the app and try again.

**Labels are shifted or run into the gap**: the printer has lost its place on
the roll. Use the printer's own re-align (feed) button, then print again. This
can happen after a job that is longer than the label. Don't change `--length`
or `--gap` to compensate.

**Text is upside down**: add `--rotate 270`.

**Print is too faint or too dark**: use `--density dark` or `--density light`.

**"unknown MDI icon"**: check the name at
[pictogrammers.com](https://pictogrammers.com/library/mdi/). The bundled font
is version 7.4.47, so icons added after it aren't available.

**Home Assistant: "… is not reachable" / Status unavailable**: the printer is
off, the phone app is connected to it, or no Bluetooth adapter or proxy is in
range. Check *Settings → Devices & services → Bluetooth* to see whether Home
Assistant sees `9529#…` advertisements.

**Home Assistant: "BREDR.ProfileUnavailable" / "classic Bluetooth instead of
Bluetooth LE"**: the printer's advertisements say it also supports classic
Bluetooth, so BlueZ on the Home Assistant host tries classic first, where the
printer offers nothing. The integration sets BlueZ's `PreferredBearer` to `le`
before each connection. That needs BlueZ with experimental features, which Home
Assistant OS has. To check it worked, open the integration and choose *Enable
debug logging*, print, and look for `PreferredBearer=le set` in the log. On a
system where BlueZ refuses it, connect through an ESPHome Bluetooth proxy
instead.

## Files

| Path | What it is |
|---|---|
| `src/wp9529/` | the Python package: `driver.py` (Bluetooth LE, `bleak`), `label.py` (renderer), `cli.py` (`wp9529-label`), `assets/` (MDI icon font 7.4.47, codepoints, license) |
| `custom_components/wp9529/` | the Home Assistant integration, with a copy of the renderer and assets |
| `examples/homeassistant/` | example script, automations and dashboard card |
| `tests/` | integration, renderer and CLI tests (Linux/WSL) |
| `tools/scan.py`, `tools/probe.py` | debugging helpers for finding the printer and sending raw commands |
| `PROTOCOL.md` | the reverse-engineered printer protocol |
