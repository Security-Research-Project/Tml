# Tml

Secure browser installation manager for [Tor Browser](https://www.torproject.org), [Mullvad Browser](https://mullvad.net/en/browser), and [LibreWolf](https://librewolf.net).

## Features

- **GPG Verification**: Every download verified against pinned GPG fingerprints in an isolated keyring
- **Zero-Trust Installation**: Failed verifications are deleted immediately; nothing unverified is installed
- **Native Integration**: Each browser gets its own app menu entry—no launcher overlay
- **Profile Preservation**: Browser profiles preserved across reinstalls and updates
- **Optional AppArmor**: Per-browser security confinement on demand
- **On-Demand Updates**: Check for updates when you want—never automatic
  
- ![Tml screenshot](/screenshot.png)

## Quick Start

```bash
git clone https://github.com/Security-Research-Project/Tml.git
cd Tml
chmod +x install.sh
./install.sh
```


## Uninstall

```
Go to your cd Tml or find it in Files than run
chmod +x uninstall.sh
./uninstall.sh
```



## Documentation

- **[DEVELOPMENT.md](./DEVELOPMENT.md)** — Installation details, security model, troubleshooting, and contributing guidelines
- **[LICENSE](./LICENSE)** — MIT License

## Disclaimer

Tml is an independent project not affiliated with, endorsed by, or sponsored by the Tor Project, Mullvad, or LibreWolf. "Tor", "Mullvad", and "LibreWolf" are trademarks of their respective projects.
