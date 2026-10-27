"""Driver for the VSON WP9529 Bluetooth LE label printer.

Protocol reverse engineered from the iLabel Android app (com.vson.ilabel):

  * GATT service 0xFFF0. Commands are written to 0xFFF1 (write without
    response); replies arrive as notifications on 0xFFF4.
  * Every command and reply starts with a one-byte opcode.

    01                                 device info / status
      <- 01 width_mm(LE16) width_dots(LE16) state err_a err_b err_c err_d ...
    04                                 reset / cancel the current job
    02 lines(LE16) offset(LE16) 00 01 density
                                       job header, continuous paper (density 24/32/39)
    02 lines(LE16) offset(LE16) 00 02 density label_mm gap_mm*10 copies
                                       job header, die-cut labels with gaps
    03 line(LE16) n data[n*width/8]    raster packet, n lines from `line`
      <- a4 / a5                       printer accepted the header
      <- a7 / a8                       pause / resume the data stream
    b1                                 MAC address
    b2                                 firmware version (the app shows it as "V" + hex)
    b4                                 auto power-off time
      <- b4 minutes ..
    b5 minutes 00                      set the auto power-off time (10-180 minutes)
      <- b5 minutes ..

  Raster data is 1 bit per pixel, MSB first, 1 = black, one print-head
  width (96 px = 12 mm at 203 dpi) per line.
"""
import asyncio
import logging

from bleak import BleakClient, BleakScanner
from PIL import Image, ImageOps

log = logging.getLogger("wp9529")

WRITE_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"
NAME_PREFIX = "9529"

DOTS_PER_MM = 8
DENSITY = {"light": 24, "normal": 32, "dark": 39}
POWER_OFF_MIN, POWER_OFF_MAX = 10, 180  # minutes, the range the iLabel app allows
LINES_PER_PACKET = 4


class PrinterError(Exception):
    pass


class Info:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.width_mm = int.from_bytes(raw[1:3], "little")
        self.width = int.from_bytes(raw[3:5], "little")
        self.state = raw[5]
        self.errors = tuple(raw[6:10])

    @property
    def busy(self):
        return self.state != 0

    @property
    def has_error(self):
        return any(self.errors)

    def __repr__(self):
        return (f"Info(width={self.width_mm} mm/{self.width} dots, state={self.state}, "
                f"errors={self.errors}, raw={self.raw.hex(' ')})")


async def find_printer(timeout=8.0):
    """Return the address of the first WP9529 found nearby."""
    dev = await BleakScanner.find_device_by_filter(
        lambda d, adv: (adv.local_name or d.name or "").startswith(NAME_PREFIX),
        timeout=timeout,
    )
    if dev is None:
        raise PrinterError("No WP9529 found. Is it on and disconnected from the phone app?")
    return dev.address


def rasterize(img: Image.Image, width: int) -> list[bytes]:
    """Turn an image `width` px wide into rows of packed 1-bit data (1 = black)."""
    if img.width != width:
        raise ValueError(f"image must be {width} px wide, got {img.width}")
    bw = ImageOps.invert(img.convert("L")).point(lambda p: 255 if p >= 128 else 0, "1")
    data = bw.tobytes()
    stride = width // 8
    return [data[i:i + stride] for i in range(0, len(data), stride)]


def build_packets(rows: list[bytes], lines_per_packet=LINES_PER_PACKET) -> list[bytes]:
    packets = []
    for start in range(0, len(rows), lines_per_packet):
        chunk = rows[start:start + lines_per_packet]
        packets.append(bytes([0x03, start & 0xFF, start >> 8, len(chunk)]) + b"".join(chunk))
    return packets


class WP9529:
    def __init__(self, address: str | None = None):
        self.address = address
        self.client: BleakClient | None = None
        self.info: Info | None = None
        self._replies: asyncio.Queue[bytes] = asyncio.Queue()
        self._resume = asyncio.Event()
        self._resume.set()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    async def connect(self):
        if self.address is None:
            self.address = await find_printer()
        self.client = BleakClient(self.address, timeout=20.0)
        await self.client.connect()
        await self.client.start_notify(NOTIFY_UUID, self._on_notify)
        self.info = await self.get_info()
        log.info("connected to %s: %r", self.address, self.info)

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()

    def _on_notify(self, _, data: bytearray):
        data = bytes(data)
        log.debug("<- %s", data.hex(" "))
        if data[:1] == b"\xa7":
            self._resume.clear()
        elif data[:1] == b"\xa8":
            self._resume.set()
        self._replies.put_nowait(data)

    async def _send(self, data: bytes):
        log.debug("-> %s", data.hex(" ") if len(data) <= 16 else f"{data[:16].hex(' ')} ... ({len(data)} B)")
        await self.client.write_gatt_char(WRITE_UUID, data, response=False)

    async def _request(self, data: bytes, opcodes: bytes, timeout=3.0) -> bytes:
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
        return f"V{(await self._request(b'\xb2', b'\xb2'))[1]:x}"

    async def power_off_minutes(self) -> int:
        """Minutes of inactivity before the printer switches itself off."""
        return (await self._request(b"\xb4", b"\xb4"))[1]

    async def set_power_off_minutes(self, minutes: int) -> int:
        """Set the auto power-off time (10-180 minutes); returns what the printer stored."""
        minutes = max(POWER_OFF_MIN, min(POWER_OFF_MAX, int(minutes)))
        return (await self._request(bytes([0xB5, minutes, 0]), b"\xb5"))[1]

    async def print_image(self, img: Image.Image, density="normal", feed_lines=0,
                          label_mm: float | None = 30, gap_mm: float = 8.5):
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
        reply = await self._request(header, b"\xa4\xa5", timeout=5.0)
        log.info("header accepted: %s", reply.hex(" "))

        self._resume.set()
        await asyncio.sleep(2.0)  # the app waits this long before the first packet
        for i, pkt in enumerate(packets):
            await self._wait_resume()
            await self._send(pkt)
            if i and (i * LINES_PER_PACKET) % 500 == 0:
                await asyncio.sleep(2.0)
        log.info("sent %d lines in %d packets", total, len(packets))

        await self._wait_done()

    async def _wait_resume(self, timeout=30.0):
        try:
            await asyncio.wait_for(self._resume.wait(), timeout)
        except TimeoutError:
            raise PrinterError("printer paused the data stream and never resumed") from None

    async def _wait_done(self, timeout=60.0):
        await asyncio.sleep(2.0)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                info = await self.get_info()
            except PrinterError:
                log.debug("status poll got no reply while printing, retrying")
                continue
            if info.has_error:
                raise PrinterError(f"printer error during print: {info!r}")
            if not info.busy:
                return
            await asyncio.sleep(1.0)
        raise PrinterError("timed out waiting for the print to finish")

    @property
    def width(self) -> int:
        return self.info.width if self.info else 96
