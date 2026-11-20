"""Model detection. The plugin targets the original ROG Ally (RC71L, Z1 and
Z1 Extreme). It still loads elsewhere, but warns, because the ring layout and
MCU behaviour differ on the Ally X / Xbox Ally."""


def _dmi(name: str) -> str:
    try:
        with open(f"/sys/devices/virtual/dmi/id/{name}") as f:
            return f.read().strip()
    except Exception:
        return ""


def _cpu() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def info() -> dict:
    product = _dmi("product_name")
    cpu = _cpu()
    # Same match HHD uses for the first-gen Ally (hhd/device/rog_ally/__init__.py)
    is_ally = "ROG Ally RC71L" in product
    chip = "Z1 Extreme" if "Z1 Extreme" in cpu else ("Z1" if "Z1" in cpu else "")
    return {
        "product": product,
        "board": _dmi("board_name"),
        "bios": _dmi("bios_version"),
        "cpu": cpu,
        "chip": chip,
        "isAlly2023": is_ally,
    }
