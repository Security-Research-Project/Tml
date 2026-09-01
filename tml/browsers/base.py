from dataclasses import dataclass


@dataclass
class Release:
    version: str
    tarball_url: str
    sig_url: str
    fingerprint: str
    sha256_url: str = None
    filename: str = None

    def __post_init__(self):
        if not self.filename:
            self.filename = self.tarball_url.rsplit("/", 1)[-1]


class BrowserSource:

    key = "base"
    display_name = "Base Browser"
    binary_name = "browser"
    desktop_categories = "Network;WebBrowser;"
    strip_top_level_dir = True

    def latest_release(self, arch: str) -> Release:
        raise NotImplementedError

    def post_install(self, install_dir: str):
        return None
