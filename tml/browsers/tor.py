import xml.etree.ElementTree as ET

from .. import config, network
from .base import BrowserSource, Release

_VERSION_FEED = (
    "https://aus1.torproject.org/torbrowser/update_3/release/"
    "Linux_x86_64-gcc3/x/ALL"
)
_DIST_BASE = "https://dist.torproject.org/torbrowser"


class TorBrowser(BrowserSource):
    key = "tor"
    display_name = "Tor Browser"
    binary_name = "start-tor-browser.desktop"
    strip_top_level_dir = True

    def latest_version(self):
        xml_bytes = network.fetch_bytes(_VERSION_FEED, max_bytes=200_000)
        root = ET.fromstring(xml_bytes)
        for update in root.iter():
            if "appVersion" in update.attrib:
                return update.attrib["appVersion"]
        raise ValueError("Could not find appVersion in Tor Browser update feed")

    def latest_release(self, arch: str) -> Release:
        if arch not in ("x86_64",):
            raise ValueError(
                f"Tor Browser has no officially distributed Linux build for "
                f"'{arch}'. Only x86_64 is currently published by the Tor "
                f"Project for Linux."
            )
        version = self.latest_version()
        filename = f"tor-browser-linux-{arch}-{version}.tar.xz"
        base = f"{_DIST_BASE}/{version}/{filename}"

        return Release(
            version=version,
            tarball_url=base,
            sig_url=base + ".asc",
            fingerprint=config.FPR_TORPROJECT,
            filename=filename,
        )

    def post_install(self, install_dir):
        return None
