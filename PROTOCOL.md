# VSON WP9529 Bluetooth LE protocol

This describes how the WP9529 thermal label printer talks over Bluetooth LE. It was
reverse engineered from the official **iLabel** Android app (v3.8, package
`com.vson.ilabel`) and checked against a real printer (firmware V50).
[wp9529.py](wp9529.py) implements it.

Every detail below has been seen working on the printer unless it is marked
**(from app code, untested)**.

## Device

| Property | Value |
|---|---|
| Advertised name | `9529#<MAC without colons>`, e.g. `9529#0952912C2090C` |
| Advertised service | `0000fff0-0000-1000-8000-00805f9b34fb` |
| Print head | 96 dots wide = 12 mm at 203 dpi (8 dots/mm) |
| Media used | die-cut labels 30 × 12 mm with an 8.5 mm gap |
| Pairing | none needed; connect directly over BLE |

The printer only advertises when no other device (such as the phone app) is
connected to it.

The app also accepts other names for printers in the same family: `95291#…`
(`JT-DA01`) and `95292#…` (`J-17`).

## GATT

| Characteristic | UUID | Properties | Use |
|---|---|---|---|
| FFF1 | `0000fff1-0000-1000-8000-00805f9b34fb` | write, write-without-response | **commands** (the app uses write-without-response) |
| FFF2 | `0000fff2-0000-1000-8000-00805f9b34fb` | write, write-without-response | unused by the app |
| FFF4 | `0000fff4-0000-1000-8000-00805f9b34fb` | notify | **replies**; enable notifications via CCCD `0x2902` |

The app asks for an MTU of `packet length + 30`. Windows negotiated 527, which
is more than enough.

## Framing

There is no framing layer, length prefix or checksum. Each GATT write is one
command, and its first byte is the opcode. Each notification is one reply, and
it starts with the opcode it answers. Multi-byte integers are **little-endian**
unless noted otherwise.

## Commands

### Status and info

| Send | Reply | Meaning |
|---|---|---|
| `01` | `01 vv vv ww ww ss e1 e2 e3 e4 xx yy zz` | device info / status (see below) |
| `b1` | `b1 m1 m2 m3 m4 m5 m6` | MAC address (the app calls it SN), e.g. `b1 95 29 12 c2 09 0c` |
| `b2` | `b2 vv` | firmware version; the app shows `"V" + hex(vv)`, so `0x50` = **V50** |
| `b3` | `b3 ss [pp]` | charging state (`0` = not charging, `3` = charging, `4` = full), then battery % on models that report it. The WP9529 replies only `b3 00`, with no level byte |
| `b4` | `b4 tt …` | auto power-off time in minutes (`tt`); the app ignores the next byte. Observed `b4 60 ea` = 96 minutes |
| `b5 tt 00` | `b5 tt 00` | **set** the auto power-off time to `tt` minutes. The app only offers 10–180 (it clamps to that range); the printer echoes the stored value. The second byte is stored too: after `b5 60 00`, `b4` replies `b4 60 00` instead of `b4 60 ea`. The app always sends `00` there |

**`01` reply fields**

| Offset | Size | Field | Observed |
|---|---|---|---|
| 0 | 1 | opcode `01` | |
| 1 | 2 | print width in mm (LE16); the app sends it to the update server as `breadth` | `0c 00` = 12 |
| 3 | 2 | print-head width in dots (LE16); sent to the update server as `pixel` | `60 00` = 96 |
| 5 | 1 | state: `0` idle, non-zero = printing | `00` / `01` |
| 6–9 | 4 | error flags, each `0`/`1` (paper out, cover open, overheat, …) | all `00` |
| 10–11 | 2 | extra model data (the app passes it on for classic-BT printers). Byte 11 matches the "V53" on the printer's self-test page, so it's probably a second (hardware or main-board) version | `01 53` |
| 12 | 1 | the app's `N` flag. It affects multi-copy handling and also enables the firmware-update check | `01` |

The app treats any non-zero error flag as an error and won't start a job. It
sends `01` automatically as soon as notifications are enabled.

### Job control

| Send | Reply | Meaning |
|---|---|---|
| `04` | `04 00` | reset / cancel the current job; sent before every job |
| `02 …` | `a5 …` or `a4 …` | job header (below) |
| `03 …` | none | raster data packet (below) |

### Job header `02`

Continuous tape (8 bytes):

```
02  LL LL  OO OO  00  01  DD
    |      |      |   |   └─ density
    |      |      |   └───── paper type 1 = continuous
    |      |      └───────── always 0 for a new job (Q)
    |      └──────────────── start offset in lines (0 for a new job; used to resume)
    └─────────────────────── total raster lines in the job (LE16)
```

Die-cut labels with gaps (11 bytes). **This is the mode to use with gap
labels**, because it makes the printer line up with each label:

```
02  LL LL  OO OO  00  02  DD  KK  GG  CC
                          |   |   |   └─ copies / label count (1)
                          |   |   └───── gap length in mm × 10 (8.5 mm → 0x55)
                          |   └───────── label length in mm (30 → 0x1e)
                          └───────────── density
```

Example used in practice: `02 f0 00 00 00 00 02 20 1e 55 01` (240 lines, gap
paper, density 32, 30 mm label, 8.5 mm gap, 1 copy).

**Density** (byte 7): the app uses `24` for light, `32` for normal and `39` for dark.
It sometimes subtracts a small model-specific adjustment.

**Header reply.** The printer answers with one of these, and the app starts
sending data after it arrives:
- `a5 PP PP OO OO QQ`: `PP` is a 16-bit status/progress value, `OO` the line
  offset to continue from, `QQ` a counter. Observed: `a5 20 03 00 00 00`.
- `a4 OO OO QQ`: resume from line offset `OO` **(from app code, untested)**.

### Raster packet `03`

```
03  SS SS  NN  <NN × (width/8) bytes>
    |      └── number of lines in this packet
    └───────── index of the first line in the packet (LE16)
```

- 1 bit per dot, **MSB first**, **1 = black**, `width/8` = 12 bytes per line.
- Line 0 comes out of the printer first.
- The app sends 4 lines per packet for 96-dot printers (52-byte packets). It
  sends 1 line per packet for most other widths.
- Packets go in order, one write each, with no reply per packet.

### Flow control

While the data streams in, the printer can push:

| Notification | Meaning |
|---|---|
| `a7` | buffer full, pause sending |
| `a8` | resume sending |

The app also waits about 2 s before the first packet and after every 500 lines.
The driver does the same. In testing, a 240-line job never triggered `a7`.

### End of job

The printer sends nothing when it finishes. The app (and the driver) waits
about 2 s, then sends `01` every second until the state byte is `0` again. The
printer reports `01` (printing) for 1–3 polls, then goes back to `00`. In gap
mode it stays busy a little longer, presumably while it feeds to the next gap.

## Full print sequence

```
host                                  printer
 |  connect, enable notify on FFF4      |
 |  01  ─────────────────────────────►  |
 |  ◄──────────────  01 0c 00 60 00 …   |  12 mm / 96 dots, idle, no errors
 |  04  ─────────────────────────────►  |
 |  ◄────────────────────────── 04 00   |
 |  01  ─────────────────────────────►  |
 |  ◄──────────────  01 … 00 00 00 00   |  check idle + no errors
 |  02 f0 00 00 00 00 02 20 1e 55 01 ►  |  header (gap paper)
 |  ◄─────────────── a5 20 03 00 00 00  |
 |  (wait ~2 s)                         |
 |  03 00 00 04 <48 bytes> ──────────►  |  lines 0–3
 |  03 04 00 04 <48 bytes> ──────────►  |  lines 4–7
 |  …                    (pause on a7, resume on a8)
 |  03 ec 00 04 <48 bytes> ──────────►  |  lines 236–239
 |  (wait ~2 s)                         |
 |  01  ─────────────────────────────►  |
 |  ◄────────────────── 01 … 01 …       |  state 1 = printing
 |  01  ─────────────────────────────►  |
 |  ◄────────────────── 01 … 00 …       |  state 0 = done
```

## Image orientation

The print head runs across the 12 mm tape, so a 30 × 12 mm label is a
**96 × 240** image (width × height), and lines run along the label's length. To
put landscape text on a label, draw it on a 240 × 96 canvas and rotate it 90°
counter-clockwise (`Image.rotate(90, expand=True)` in Pillow). The right-hand
end of the landscape canvas then prints first.

## Alignment notes

- With the **continuous** header (`… 01 DD`) on gap labels, printing started
  about 11 mm into each label. The extra length ran into the gap and onto the
  next label. The offset was the same every time; it wasn't drift.
- With the **gap** header (`… 02 DD 1e 55 01`), labels lined up correctly,
  including several in a row.
- If a job is longer than the label (e.g. 40 mm on 30 mm stock), the printer
  loses its place on the roll. Re-align with the printer's own button
  afterwards.

## Other opcodes seen in the app (untested)

These appear in the app's code. Their purpose is guessed from context, and none
of them has been tried on the printer.

| Opcode | Guess |
|---|---|
| `07 00` / `07 01` | toggle a printer setting (sent by the BLE layer) |
| `09` | query |
| `80 …` | firmware-update block (`0x80`, then 4-byte and 4-byte big-endian values) |
| `81 …` | firmware-update data frames (index BE32, length, data, 8-bit sum) |
| `82 82` | end of firmware update |
| `ac` | "print check" before a job, used by other models |
| `b3`, `b5 xx yy`, `b6`, `b7 lo hi`, `bf …` | settings; `b7` takes a value 10–1000 (maybe the auto-off time) |
| `c1 xx`, `c2`, `cb …`, `cc`, `ce`, `cf` | Wi-Fi printer models |
| `cd len16 "ssid:…,passwd:…\0"` | set Wi-Fi credentials (Wi-Fi models) |
| `d1`, `d2`, `d3` | misc queries |
| `e1` | multi-part info query (replies `e1 idx …`) |

Don't send the firmware-update opcodes (`80`/`81`/`82`) without knowing exactly
what they do.

## Firmware updates

The app asks Vson's cloud whether newer firmware exists. That request doesn't
involve the printer:

```
POST https://apis.myvsoncloud.com:16082/vc-pms-ws-1.0.2/api/m/queryAppNewestVersionPrinter
Content-Type: application/x-www-form-urlencoded
headers: apv=3.8  apt=109  md=WP2810  pid=cup033  ost=2  cm=1  language=en

language=en&model=9529&pixel=96&chipModel=0&breadth=12
```

- `model` is the number from the advertised name.
- `pixel` and `breadth` come from the `01` reply.
- `chipModel` is `0` for Bluetooth LE printers.
- Without `apv`, the server answers `{"retCode":"1001","result":"app version not null"}`.

The reply is `{"retCode":"0","result":{"versionCode":…,"versionName":…,"url":…,"describe":…}}`.
The app offers an update only when `result` is present and `versionCode` is greater
than the `b2` firmware version. It then downloads `url` and flashes the image with
the `80`/`81`/`82` opcodes.

**Checked 2026-10-25:** the server returned `{"retCode":"0"}` with no `result`
for this printer (firmware V50). So no newer firmware is published for it.

## Where this came from

All of this is in the decompiled package `com.vson.ilabel.ui.bt`:
- `VsonPtBLE`: GATT setup, UUIDs, notifications, MTU, write type.
- `t2`: the job state machine.
  - `H0`: builds the header.
  - `j1`: builds the packets.
  - `s0`: send loop.
  - `i0`: reply dispatcher.
  - `h0`: parses the `01` reply.
- `l1`: per-model settings.
  - The 9529 is in the group that uses the 11-byte header.
  - Defaults: label length 25 mm, gap 8.5 mm.
- `com.vson.ilabel.util.t.t(Bitmap, int)`: turns the image into raster packets.
