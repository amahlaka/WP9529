"""Print labels on a VSON WP9529 from the command line.

Examples:
    wp9529-label --info                                     # printer status
    wp9529-label --power-off 30                             # switch off after 30 idle minutes
    wp9529-label --title Router --text "admin / see vault" --icon mdi:router-wireless
    wp9529-label --qr "WIFI:T:WPA;S:Home;P:secret;;" --text "Guest Wi-Fi"
    wp9529-label --qr https://example.com --icon mdi:link --copies 3
    wp9529-label --title Spices --preview previews          # render a PNG only
    wp9529-label --image my_label.png                       # an image 96 px wide
"""
import argparse
import asyncio
import logging
from pathlib import Path

from PIL import Image

from .driver import DENSITY, POWER_OFF_MAX, POWER_OFF_MIN, WP9529, PrinterError
from .label import render_label


def power_off_minutes(value: str) -> int:
    minutes = int(value)
    if not POWER_OFF_MIN <= minutes <= POWER_OFF_MAX:
        raise argparse.ArgumentTypeError(f"must be {POWER_OFF_MIN}-{POWER_OFF_MAX} minutes")
    return minutes


def add_print_options(p: argparse.ArgumentParser) -> None:
    """Options about the roll and the printer, shared with other label tools."""
    p.add_argument("--length", type=float, default=30, help="label length in mm (default 30)")
    p.add_argument("--gap", type=float, default=8.5, help="gap between labels in mm (default 8.5)")
    p.add_argument("--continuous", action="store_true", help="continuous tape instead of die-cut labels")
    p.add_argument("--rotate", type=int, default=90, choices=[90, 270], help="flip if text prints upside down")
    p.add_argument("--density", default="normal", choices=list(DENSITY))
    p.add_argument("--feed", type=int, default=0, help="extra blank lines after the label")
    p.add_argument("--copies", type=int, default=1, help="copies of each label")
    p.add_argument("--preview", metavar="DIR", help="save rendered labels as PNGs in DIR instead of printing")
    p.add_argument("--address", help="printer BLE address (default: scan for it)")
    p.add_argument("-v", "--verbose", action="store_true", help="log every Bluetooth packet")


def save_previews(jobs: list[tuple[str, Image.Image]], directory: str) -> None:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for name, img in jobs:
        img.save(out / f"{name}.png")
    print(f"saved {len(jobs)} preview(s) to {out}")


async def print_jobs(jobs: list[tuple[str, Image.Image]], args, info: bool = False,
                     power_off: int | None = None) -> None:
    """Connect once and print each (name, image) job `args.copies` times."""
    async with WP9529(args.address) as printer:
        print(f"printer {printer.address}: firmware {await printer.firmware_version()}")
        if power_off is not None:
            stored = await printer.set_power_off_minutes(power_off)
            print(f"auto power-off set to {stored} minutes")
        elif info:
            print(f"auto power-off after {await printer.power_off_minutes()} minutes")
        for name, img in jobs:
            for _ in range(args.copies):
                await printer.print_image(img, density=args.density, feed_lines=args.feed,
                                          label_mm=None if args.continuous else args.length,
                                          gap_mm=args.gap)
            print(f"printed {name}" + (f" x{args.copies}" if args.copies > 1 else ""))


async def run(args) -> None:
    jobs: list[tuple[str, Image.Image]] = []
    if args.image:
        jobs.append((Path(args.image).stem, Image.open(args.image)))
    elif args.title or args.text or args.qr or args.icon:
        img = render_label(title=args.title, text=args.text, qr=args.qr, icon=args.icon,
                           length_mm=args.length, rotate=args.rotate)
        jobs.append(("label", img))
    if args.preview:
        if not jobs:
            raise ValueError("nothing to preview: give --title, --text, --qr, --icon or --image")
        save_previews(jobs, args.preview)
        return
    if not jobs and not args.info and args.power_off is None:
        raise ValueError("nothing to do: give --title, --text, --qr, --icon, --image, --info or --power-off")
    await print_jobs(jobs, args, info=args.info, power_off=args.power_off)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="wp9529-label", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--title", default="", help="large text")
    p.add_argument("--text", default="", help="smaller text (or the only text)")
    p.add_argument("--qr", help="any text to encode as a QR code")
    p.add_argument("--icon", help="MDI icon, e.g. mdi:tools (https://pictogrammers.com/library/mdi/)")
    p.add_argument("--image", help="print an existing image (must be 96 px wide)")
    p.add_argument("--info", action="store_true", help="show the printer's firmware and auto power-off time")
    p.add_argument("--power-off", type=power_off_minutes, metavar="MIN",
                   help=f"set the printer's auto power-off time ({POWER_OFF_MIN}-{POWER_OFF_MAX} minutes)")
    add_print_options(p)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(message)s")
    try:
        asyncio.run(run(args))
    except (PrinterError, ValueError, OSError) as e:
        raise SystemExit(f"error: {e}") from None


if __name__ == "__main__":
    main()
