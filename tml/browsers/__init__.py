from .librewolf import LibreWolf
from .mullvad import MullvadBrowser
from .tor import TorBrowser

REGISTRY = {
    "tor": TorBrowser(),
    "mullvad": MullvadBrowser(),
    "librewolf": LibreWolf(),
}

ORDER = ["tor", "mullvad", "librewolf"]
