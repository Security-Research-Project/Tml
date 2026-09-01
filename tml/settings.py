import json
import logging
import os

from . import config

log = logging.getLogger("tml.settings")

DEFAULTS = {
    "sandbox_mode": "apparmor",
}

VALID_SANDBOX_MODES = ("apparmor", "none")


def load():
    if os.path.exists(config.SETTINGS_FILE):
        try:
            with open(config.SETTINGS_FILE) as f:
                data = json.load(f)
            merged = dict(DEFAULTS)
            for k in DEFAULTS:
                if k in data:
                    merged[k] = data[k]
            if merged["sandbox_mode"] not in VALID_SANDBOX_MODES:
                merged["sandbox_mode"] = "apparmor"
            return merged
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not read settings file, using defaults: %s", e)
    return dict(DEFAULTS)


def save(settings):
    os.makedirs(config.CONFIG_DIR, mode=0o700, exist_ok=True)
    clean = dict(DEFAULTS)
    for k in DEFAULTS:
        if k in settings:
            clean[k] = settings[k]
    tmp = config.SETTINGS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(clean, f, indent=2)
    os.replace(tmp, config.SETTINGS_FILE)
    return clean
