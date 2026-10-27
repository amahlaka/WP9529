"""Scan for nearby BLE devices and dump the GATT table of a chosen one.

Usage:
    python tools/scan.py              # list nearby devices
    python tools/scan.py <ADDRESS>    # dump services/characteristics of a device
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner


async def scan():
    found = await BleakScanner.discover(timeout=8.0, return_adv=True)
    for dev, adv in sorted(found.values(), key=lambda x: -(x[1].rssi or -999)):
        print(f"{dev.address}  rssi={adv.rssi:>4}  name={adv.local_name or dev.name!r}"
              f"  uuids={adv.service_uuids}  mfr={ {k: v.hex() for k, v in adv.manufacturer_data.items()} }")


async def dump(address):
    async with BleakClient(address, timeout=20.0) as client:
        for svc in client.services:
            print(f"[service] {svc.uuid}  {svc.description}")
            for ch in svc.characteristics:
                line = f"    [char] {ch.uuid}  handle={ch.handle}  props={ch.properties}"
                if "read" in ch.properties:
                    try:
                        val = await client.read_gatt_char(ch)
                        line += f"  value={val!r}"
                    except Exception as e:
                        line += f"  read-error={e}"
                print(line)


if __name__ == "__main__":
    asyncio.run(dump(sys.argv[1]) if len(sys.argv) > 1 else scan())
