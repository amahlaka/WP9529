"""Send the iLabel device-info request (0x01) and print the raw reply."""
import asyncio
import sys

from bleak import BleakClient

ADDRESS = "95:29:12:C2:09:0C"
WRITE = "0000fff1-0000-1000-8000-00805f9b34fb"
NOTIFY = "0000fff4-0000-1000-8000-00805f9b34fb"


async def main(cmds):
    async with BleakClient(ADDRESS, timeout=20.0) as client:
        print(f"mtu={client.mtu_size}")
        await client.start_notify(NOTIFY, lambda _, d: print(f"  <- {bytes(d).hex(' ')}"))
        await asyncio.sleep(0.5)
        for cmd in cmds:
            print(f"-> {cmd.hex(' ')}")
            await client.write_gatt_char(WRITE, cmd, response=False)
            await asyncio.sleep(1.5)


if __name__ == "__main__":
    cmds = [bytes.fromhex(a) for a in sys.argv[1:]] or [b"\x01"]
    asyncio.run(main(cmds))
