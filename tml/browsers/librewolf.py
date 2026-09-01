import json
import re

from .. import config, network
from .base import BrowserSource, Release

_RELEASES_API = "https://codeberg.org/api/v1/repos/librewolf/bsys6/releases?limit=5"

_ARCH_MAP = {"x86_64": "x86_64", "aarch64": "arm64"}


class LibreWolf(BrowserSource):
    key = "librewolf"
    display_name = "LibreWolf"
    binary_name = "librewolf"
    strip_top_level_dir = True

    def latest_release(self, arch: str) -> Release:
        lw_arch = _ARCH_MAP.get(arch)
        if not lw_arch:
            raise ValueError(f"LibreWolf publishes no Linux build for '{arch}'.")

        raw = network.fetch_bytes(_RELEASES_API, max_bytes=1_000_000)
        releases = json.loads(raw)
        if not releases:
            raise ValueError("Could not find any LibreWolf releases.")

        release = next((r for r in releases if not r.get("prerelease")
                         and not r.get("draft")), releases[0])

        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        pattern = re.compile(
            rf"^librewolf-[\w.\-]+-linux-{re.escape(lw_arch)}-package\.tar\.xz$"
        )
        tarball_name = next((n for n in assets if pattern.match(n)), None)
        if not tarball_name:
            raise ValueError(
                f"Could not find a LibreWolf linux-{lw_arch} package tarball "
                f"in release '{release.get('tag_name')}'."
            )
        sig_name = tarball_name + ".sig"
        sha_name = tarball_name + ".sha256sum"
        if sig_name not in assets:
            raise ValueError(
                f"LibreWolf release {release.get('tag_name')} is missing a "
                f"detached signature - refusing to install unsigned binaries."
            )

        return Release(
            version=release.get("tag_name", "unknown"),
            tarball_url=assets[tarball_name],
            sig_url=assets[sig_name],
            fingerprint=config.FPR_LIBREWOLF,
            sha256_url=assets.get(sha_name),
            filename=tarball_name,
        )

    def post_install(self, install_dir):
        return None
