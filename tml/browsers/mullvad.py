import re

from .. import config, network
from .base import BrowserSource, Release

_ARCH_MAP = {"x86_64": "linux-x86_64"}
_DOWNLOAD_BASE = "https://mullvad.net/en/download/browser"
_FILENAME_RE = re.compile(r"mullvad-browser-linux-[\w.]+-(?P<version>[\w.]+)\.tar\.xz$")


class MullvadBrowser(BrowserSource):
    key = "mullvad"
    display_name = "Mullvad Browser"
    binary_name = "start-mullvad-browser.desktop"
    strip_top_level_dir = True

    def latest_release(self, arch: str) -> Release:
        mv_arch = _ARCH_MAP.get(arch)
        if not mv_arch:
            raise ValueError(
                f"Mullvad Browser has no officially distributed stable "
                f"Linux build for '{arch}'."
            )

        tarball_url = network.resolve_redirect(f"{_DOWNLOAD_BASE}/{mv_arch}/latest")

        filename = tarball_url.rsplit("/", 1)[-1]
        match = _FILENAME_RE.search(filename)
        if not match:
            raise ValueError(
                f"Could not parse a Mullvad Browser version from resolved "
                f"download URL: {tarball_url}"
            )
        version = match.group("version")

        # Signature is "<tarball>.asc" (Mullvad Browser is signed by
        # the same key as Tor Browser), derived from the resolved URL.
        sig_url = tarball_url + ".asc"

        return Release(
            version=version,
            tarball_url=tarball_url,
            sig_url=sig_url,
            fingerprint=config.FPR_TORPROJECT,
            filename=filename,
        )

    def post_install(self, install_dir):
        return None
