import json
import os
import tempfile

import decky

PATH = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")


def load() -> dict:
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        decky.logger.error(f"settings load failed: {e}")
        return {}


def save(data: dict) -> None:
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(PATH), prefix=".settings.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, PATH)
