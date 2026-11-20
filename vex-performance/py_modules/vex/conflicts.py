"""Spot other plugins/daemons that also write TDP/GPU so we don't fight them."""
import os
import subprocess

import decky

KNOWN = {
    "SimpleDeckyTDP": "TDP/GPU",
    "PowerTools": "TDP/GPU/CPU",
    "PowerControl": "TDP/GPU",
    "decky-lsfg-vk": "lsfg-vk profiles (compatible, shares conf.toml)",
    "Decky LSFG-VK": "lsfg-vk profiles (compatible, shares conf.toml)",
}


def _service_active(name):
    try:
        r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def detect():
    found = []
    plugins_dir = os.path.join(decky.DECKY_USER_HOME, "homebrew", "plugins")
    try:
        for entry in os.listdir(plugins_dir):
            for key, what in KNOWN.items():
                if entry.lower() == key.lower():
                    found.append({"name": entry, "controls": what})
    except Exception:
        pass
    return {
        "plugins": found,
        "tuned_ppd": _service_active("power-profiles-daemon") or _service_active("tuned-ppd"),
    }
