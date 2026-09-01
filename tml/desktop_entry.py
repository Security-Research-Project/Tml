import logging
import os
import shutil
import subprocess

from . import config, installer, sandbox, settings

log = logging.getLogger("tml.desktop_entry")

_ENTRY_PREFIX = "tml-"
_ICON_FILENAMES = (
    "default128.png", "default64.png", "default48.png",
    "icon128.png", "icon64.png", "icon48.png",
    "default.png", "icon.png",
)


def entry_path(browser):
    return os.path.join(config.DESKTOP_ENTRY_DIR, f"{_ENTRY_PREFIX}{browser.key}.desktop")


def find_icon(install_dir):
    candidates = []
    for root, _dirs, files in os.walk(install_dir):
        for fn in files:
            if fn.lower() in _ICON_FILENAMES:
                candidates.append(os.path.join(root, fn))
    if not candidates:
        return None
    candidates.sort(key=lambda p: -os.path.getsize(p))
    return candidates[0]


def _quote(arg):
    if arg and not any(c in arg for c in " \t\"'\\$`"):
        return arg
    return "'" + arg.replace("'", "'\\''") + "'"


def write_entry(browser):
    install_dir = os.path.join(config.INSTALL_ROOT, browser.key)
    exe = installer.find_launch_script(browser, install_dir)
    mode = settings.load().get("sandbox_mode", "apparmor")
    argv, description = sandbox.build_launch_command(browser, exe, mode=mode)
    exec_line = " ".join(_quote(a) for a in argv)

    icon_path = find_icon(install_dir)
    if not icon_path:
        log.warning(
            "No bundled icon found in %s for %s; Icon= is omitted rather "
            "than set to a fabricated placeholder", install_dir, browser.key
        )

    os.makedirs(config.DESKTOP_ENTRY_DIR, exist_ok=True)
    icon_line = f"Icon={icon_path}\n" if icon_path else ""
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={browser.display_name}\n"
        f"Exec={exec_line}\n"
        f"{icon_line}"
        "Terminal=false\n"
        f"Categories={browser.desktop_categories}\n"
        f"Path={install_dir}\n"
    )
    path = entry_path(browser)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o644)
    _refresh_desktop_db()
    log.info("Wrote independent desktop entry for %s (%s) at %s", browser.key, description, path)
    return path


def remove_entry(browser):
    path = entry_path(browser)
    if os.path.exists(path):
        os.remove(path)
        _refresh_desktop_db()
        log.info("Removed desktop entry for %s", browser.key)


def regenerate_all_installed():
    from .browsers import ORDER, REGISTRY
    updated = []
    for key in ORDER:
        b = REGISTRY[key]
        if installer.is_installed(b):
            write_entry(b)
            updated.append(key)
    return updated


def _refresh_desktop_db():
    if shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", config.DESKTOP_ENTRY_DIR],
            capture_output=True,
        )
