"""Ring colour over the MCU's own LED report (fallback for kernels that clamp
multi_intensity).

Linux 7.2+ caps each multi_intensity value at multi_max_intensity, which
defaults to max_brightness (255). hid-asus-ally packs 0xRRGGBB into one value
per zone and doesn't raise that cap, so every colour reaching the driver turns
into a shade of blue. This module sends the exact report the driver itself
sends for the rings (hid-asus-ally.c ally_rgb_do_work; HHD uses the same):

    feature report 0x5A, code page 0xD1, cmd 0x08 (set LEDs), len 0x0C,
    then R,G,B for each of the 4 zones, zero-padded to 64 bytes.

Nothing else: no mode changes, no EC/MCU settings, no firmware. The MCU keeps
these colours only until reboot or sleep; the restore unit sends them again.

Stdlib only so the boot/resume restore unit can run this file directly:
    python3 ring_hid.py R G B R G B R G B R G B
"""
import fcntl
import os
import sys

VENDOR = "00000B05"
PRODUCTS = ("00001ABE", "00001B4C")   # ROG Ally (RC71L), Ally X
REPORT_SIZE = 64
HEADER = bytes([0x5A, 0xD1, 0x08, 0x0C])


def _hiocsfeature(n):
    # _IOC(_IOC_WRITE | _IOC_READ, 'H', 0x06, n)
    return (3 << 30) | (n << 16) | (ord("H") << 8) | 0x06


def find_node():
    """/dev/hidrawN of the Ally MCU interface that declares report ID 0x5A."""
    base = "/sys/class/hidraw"
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return None
    for n in names:
        try:
            with open(f"{base}/{n}/device/uevent") as f:
                ue = f.read().upper()
            if f":{VENDOR}:" not in ue or not any(p in ue for p in PRODUCTS):
                continue
            with open(f"{base}/{n}/device/report_descriptor", "rb") as f:
                desc = f.read()
            if b"\x85\x5a" in desc:   # Report ID (0x5A)
                return f"/dev/{n}"
        except OSError:
            continue
    return None


def available() -> bool:
    return find_node() is not None


def build(values):
    vals = [max(0, min(255, int(v))) for v in values]
    if len(vals) != 12:
        raise ValueError("need 12 values (R G B x 4 zones)")
    return (HEADER + bytes(vals)).ljust(REPORT_SIZE, b"\0")


def send(values, node=None):
    node = node or find_node()
    if not node:
        raise OSError("Ally MCU hidraw interface not found")
    buf = bytearray(build(values))
    fd = os.open(node, os.O_RDWR)
    try:
        fcntl.ioctl(fd, _hiocsfeature(len(buf)), buf)
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        send(sys.argv[1:])
    except Exception as e:
        print(f"ring_hid: {e}", file=sys.stderr)
        sys.exit(1)
