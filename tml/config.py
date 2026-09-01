import os
import platform

APP_ID = "org.tml.Tml"
APP_NAME = "Tml"
VERSION = "0.1.0"

HOME = os.path.expanduser("~")
XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config"))
XDG_CACHE_HOME = os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache"))
XDG_DATA_HOME = os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local", "share"))

CONFIG_DIR = os.path.join(XDG_CONFIG_HOME, "tml")
CACHE_DIR = os.path.join(XDG_CACHE_HOME, "tml")
DATA_DIR = os.path.join(XDG_DATA_HOME, "tml")

DOWNLOAD_DIR = os.path.join(CACHE_DIR, "downloads")
GNUPG_HOMEDIR = os.path.join(DATA_DIR, "gnupg")
INSTALL_ROOT = os.path.join(DATA_DIR, "browsers")
LOG_FILE = os.path.join(CACHE_DIR, "tml.log")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
DESKTOP_ENTRY_DIR = os.path.join(XDG_DATA_HOME, "applications")


_PRIVATE_DIRS = [CONFIG_DIR, CACHE_DIR, DATA_DIR, DOWNLOAD_DIR, GNUPG_HOMEDIR,
                 INSTALL_ROOT]


def ensure_dirs():
    for d in _PRIVATE_DIRS:
        os.makedirs(d, mode=0o700, exist_ok=True)
        # makedirs only sets mode on creation, not on a pre-existing dir.
        os.chmod(d, 0o700)
    os.makedirs(DESKTOP_ENTRY_DIR, exist_ok=True)


def detect_arch():
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    return machine


FPR_TORPROJECT = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"

FPR_LIBREWOLF = "662E3CDD6FE329002D0CA5BB40339DD82B12EF16"

KEY_SOURCES = {
    FPR_TORPROJECT: [
        "https://torproject.org/.well-known/openpgpkey/hu/"
        "kounek7zrdx745qydx6p59t9mqjpuhdf?l=torbrowser",
        "https://keys.openpgp.org/vks/v1/by-fingerprint/" + FPR_TORPROJECT,
    ],
    FPR_LIBREWOLF: [
        "https://repo.librewolf.net/pubkey.gpg",
        "https://keys.openpgp.org/vks/v1/by-fingerprint/" + FPR_LIBREWOLF,
    ],
}

BUNDLED_KEY_FILES = {
    FPR_TORPROJECT: "torproject.asc",
    FPR_LIBREWOLF: "pubkey.gpg",
}

USER_AGENT = f"{APP_NAME}/{VERSION} requests"
