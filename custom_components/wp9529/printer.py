"""Bluetooth LE driver for the VSON WP9529, on Home Assistant's Bluetooth stack.

Same protocol as the standalone wp9529.py; see PROTOCOL.md in the Labeler
project for the byte-level description.
"""
from __future__ import annotations

import asyncio
import logging

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from PIL import Image, ImageOps

from .bluez import async_prefer_le

_LOGGER = logging.getLogger(__name__)

WRITE_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"

DOTS_PER_MM = 8
DENSITY = {"light": 24, "normal": 32, "dark": 39}
POWER_OFF_MIN, POWER_OFF_MAX = 10, 180  # minutes, the range the iLabel app allows
LINES_PER_PACKET = 4


class PrinterError(Exception):
    """The printer reported a problem or stopped answering."""


class Info:
    """Parsed reply to the 0x01 status request."""

    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.width_mm = int.from_bytes(raw[1:3], "little")
        self.width = int.from_bytes(raw[3:5], "little")
        self.state = raw[5]
        self.errors = tuple(raw[6:10])

    @property
    def busy(self) -> bool:
        return self.state != 0

    @property
    def has_error(self) -> bool:
        return any(self.errors)

    def __repr__(self) -> str:
        return (f"Info(width={self.width_mm} mm/{self.width} dots, state={self.state}, "
                f"errors={self.errors}, raw={self.raw.hex(' ')})")


def rasterize(img: Image.Image, width: int) -> list[bytes]:
    """Turn an image `width` px wide into rows of packed 1-bit data (1 = black)."""
    if img.width != width:
        raise ValueError(f"image must be {width} px wide, got {img.width}")
    bw = ImageOps.invert(img.convert("L")).point(lambda p: 255 if p >= 128 else 0, "1")
    data = bw.tobytes()
    stride = width // 8
    return [data[i:i + stride] for i in range(0, len(data), stride)]


def build_packets(rows: list[bytes], lines_per_packet: int = LINES_PER_PACKET) -> list[bytes]:
    packets = []
    for start in range(0, len(rows), lines_per_packet):
        chunk = rows[start:start + lines_per_packet]
        packets.append(bytes([0x03, start & 0xFF, start >> 8, len(chunk)]) + b"".join(chunk))
    return packets


class WP9529:
    """One connection to the printer; use as an async context manager."""

    def __init__(self, ble_device: BLEDevice) -> None:
        self.ble_device = ble_device
        self.client: BleakClientWithServiceCache | None = None
        self.info: Info | None = None
        self._replies: asyncio.Queue[bytes] = asyncio.Queue()
        self._resume = asyncio.Event()
        self._resume.set()

    async def __aenter__(self) -> WP9529:
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        await async_prefer_le(self.ble_device)
        self.client = await establish_connection(
            BleakClientWithServiceCache, self.ble_device,
            self.ble_device.name or self.ble_device.address, max_attempts=3)
        await self.client.start_notify(NOTIFY_UUID, self._on_notify)
        self.info = await self.get_info()
        _LOGGER.debug("connected to %s: %r", self.ble_device.address, self.info)

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected:
            await self.client.disconnect()

    def _on_notify(self, _, data: bytearray) -> None:
        data = bytes(data)
        _LOGGER.debug("<- %s", data.hex(" "))
        if data[:1] == b"\xa7":
            self._resume.clear()
        elif data[:1] == b"\xa8":
            self._resume.set()
        self._replies.put_nowait(data)

    async def _send(self, data: bytes) -> None:
        await self.client.write_gatt_char(WRITE_UUID, data, response=False)

    async def _request(self, data: bytes, opcodes: bytes, timeout: float = 3.0) -> bytes:
        """Send a command and wait for a reply starting with one of `opcodes`."""
        while not self._replies.empty():
            self._replies.get_nowait()
        await self._send(data)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise PrinterError(f"no reply to {data[:1].hex()} (wanted {opcodes.hex()})")
            try:
                reply = await asyncio.wait_for(self._replies.get(), remaining)
            except TimeoutError:
                raise PrinterError(f"no reply to {data[:1].hex()} (wanted {opcodes.hex()})") from None
            if reply[0] in opcodes:
                return reply

    async def get_info(self) -> Info:
        return Info(await self._request(b"\x01", b"\x01"))

    async def firmware_version(self) -> str:
        reply = await self._request(b"\xb2", b"\xb2")
        return f"V{reply[1]:x}"

    async def charging_state(self) -> int:
        """0 = not charging, 3 = charging, 4 = full (codes from the iLabel app)."""
        return (await self._request(b"\xb3", b"\xb3"))[1]

    async def power_off_minutes(self) -> int:
        """Minutes of inactivity before the printer switches itself off (b4)."""
        return (await self._request(b"\xb4", b"\xb4"))[1]

    async def set_power_off_minutes(self, minutes: int) -> int:
        """Set the auto power-off time (b5, 10-180 minutes); returns what the printer stored."""
        minutes = max(POWER_OFF_MIN, min(POWER_OFF_MAX, int(minutes)))
        return (await self._request(bytes([0xB5, minutes, 0]), b"\xb5"))[1]

    @property
    def width(self) -> int:
        return self.info.width if self.info else 96

    async def print_image(self, img: Image.Image, density: str = "normal", feed_lines: int = 0,
                          label_mm: float | None = 30, gap_mm: float = 8.5) -> None:
        """Print one label. `img` must be exactly print-head wide (see .width).

        With `label_mm` set the job is sent as gap paper so the printer lines up
        with the die-cut labels; pass label_mm=None for continuous tape.
        """
        level = DENSITY.get(density, density)
        rows = rasterize(img, self.width)
        rows += [bytes(self.width // 8)] * feed_lines
        packets = build_packets(rows)

        await self._send(b"\x04")
        await asyncio.sleep(0.3)
        info = await self.get_info()
        if info.has_error:
            raise PrinterError(f"printer reports an error (out of paper / cover open?): {info!r}")
        if info.busy:
            raise PrinterError(f"printer is busy: {info!r}")

        total = len(rows)
        if label_mm:
            header = bytes([0x02, total & 0xFF, total >> 8, 0, 0, 0, 0x02, level,
                            round(label_mm), round(gap_mm * 10), 1])
        else:
            header = bytes([0x02, total & 0xFF, total >> 8, 0, 0, 0, 0x01, level])
        await self._request(header, b"\xa4\xa5", timeout=5.0)

        self._resume.set()
        await asyncio.sleep(2.0)  # the app waits this long before the first packet
        for i, pkt in enumerate(packets):
            await self._wait_resume()
            await self._send(pkt)
            if i and (i * LINES_PER_PACKET) % 500 == 0:
                await asyncio.sleep(2.0)
        await self._wait_done()

    async def _wait_resume(self, timeout: float = 30.0) -> None:
        try:
            await asyncio.wait_for(self._resume.wait(), timeout)
        except TimeoutError:
            raise PrinterError("printer paused the data stream and never resumed") from None

    async def _wait_done(self, timeout: float = 60.0) -> None:
        await asyncio.sleep(2.0)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                info = await self.get_info()
            except PrinterError:
                continue
            if info.has_error:
                raise PrinterError(f"printer error during print: {info!r}")
            if not info.busy:
                return
            await asyncio.sleep(1.0)
        raise PrinterError("timed out waiting for the print to finish")
