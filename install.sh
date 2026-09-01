#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Detecting package manager..."
if command -v dnf >/dev/null 2>&1; then
    PM="dnf"
    INSTALL_CMD="sudo dnf install -y"
    PKGS="python3 python3-pip gtk4 libadwaita gnupg2 xz desktop-file-utils polkit"
    OPTIONAL_PKGS="apparmor"
elif command -v apt-get >/dev/null 2>&1; then
    PM="apt"
    INSTALL_CMD="sudo apt-get install -y"
    PKGS="python3 python3-pip python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gnupg xz-utils desktop-file-utils policykit-1"
    OPTIONAL_PKGS="apparmor-utils"
elif command -v pacman >/dev/null 2>&1; then
    PM="pacman"
    INSTALL_CMD="sudo pacman -S --needed --noconfirm"
    PKGS="python python-pip python-gobject gtk4 libadwaita gnupg xz desktop-file-utils polkit"
    OPTIONAL_PKGS="apparmor"
elif command -v zypper >/dev/null 2>&1; then
    PM="zypper"
    INSTALL_CMD="sudo zypper install -y"
    PKGS="python3 python3-pip gtk4 libadwaita gpg2 xz desktop-file-utils polkit"
    OPTIONAL_PKGS="apparmor"
else
    PM=""
fi

if [ -z "$PM" ]; then
    echo
    echo "Could not detect dnf, apt, pacman, or zypper on this system."
    echo "Tml has no distro-specific code, but this script only knows"
    echo "how to drive those four package managers. Install these manually"
    echo "with your distro's tools and re-run this script:"
    echo "  - Python 3.9+, venv, pip"
    echo "  - PyGObject + GTK 4 + libadwaita (the 'gi' Python module with"
    echo "    Gtk 4.0 and Adw 1) - this needs to be a SYSTEM package, not"
    echo "    a pip one; it's not reliably pip-installable"
    echo "  - GnuPG (gpg)"
    echo "  - xz / liblzma tools"
    echo "  - desktop-file-utils (update-desktop-database)"
    echo "  - polkit (for pkexec, used when you turn on AppArmor in"
    echo "    Preferences - it needs one privileged copy+load of the"
    echo "    generated profile)"
    echo
    echo "Or use the Flatpak build in packaging/flatpak/ instead, which"
    echo "needs none of this detection."
    exit 1
fi

echo "==> Detected: $PM"
echo "==> Installing system dependencies (requires sudo)..."
$INSTALL_CMD $PKGS
$INSTALL_CMD $OPTIONAL_PKGS || echo "    (optional AppArmor userspace tools not available via $PM - skipping, not fatal)"

VENV_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/tml/venv"
echo "==> Setting up Tml's own Python environment at ${VENV_DIR}..."
python3 -m venv --system-site-packages "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
echo "==> Installing Tml into it..."
"${VENV_DIR}/bin/pip" install --upgrade "${SCRIPT_DIR}"

BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}"
ln -sf "${VENV_DIR}/bin/tml" "${BIN_DIR}/tml"

echo "==> Installing desktop menu entry (freedesktop.org spec)..."
mkdir -p "${HOME}/.local/share/applications"
if [ -f "${SCRIPT_DIR}/packaging/org.tml.Tml.desktop" ]; then
    sed "s|^Exec=tml\$|Exec=${VENV_DIR}/bin/tml|" \
        "${SCRIPT_DIR}/packaging/org.tml.Tml.desktop" \
        > "${HOME}/.local/share/applications/org.tml.Tml.desktop"
else
    # Fallback for installs where packaging/ is not available (e.g. pip-installed)
    cat > "${HOME}/.local/share/applications/org.tml.Tml.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Tml
GenericName=Browser Installer
Comment=Fetch and GPG-verify Tor Browser, Mullvad Browser, or LibreWolf from official sources
Exec=${VENV_DIR}/bin/tml
Icon=org.tml.Tml
Terminal=false
Categories=Network;WebBrowser;Utility;
Path=${HOME}
StartupWMClass=Tml
Keywords=tor;mullvad;librewolf;browser;privacy;
EOF
fi
echo "==> Installing app icon (freedesktop.org hicolor theme)..."
ICON_DEST_DIR="${HOME}/.local/share/icons/hicolor"
mkdir -p "${ICON_DEST_DIR}/scalable/apps" "${ICON_DEST_DIR}/symbolic/apps"
cp "${SCRIPT_DIR}/tml/data/icons/org.tml.Tml.svg" \
   "${ICON_DEST_DIR}/scalable/apps/org.tml.Tml.svg"
cp "${SCRIPT_DIR}/tml/data/icons/org.tml.Tml-symbolic.svg" \
   "${ICON_DEST_DIR}/symbolic/apps/org.tml.Tml-symbolic.svg"
gtk-update-icon-cache "${ICON_DEST_DIR}" >/dev/null 2>&1 || true

update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true

echo
echo "==> Done."
echo "    If '${BIN_DIR}' is not already on your PATH, add this to your shell rc file:"
echo "        export PATH=\"${BIN_DIR}:\$PATH\""
echo
echo "    Tml is GUI-only, on purpose - there is no CLI. Launch it from"
echo "    your application menu as \"Tml\", or run:"
echo "        tml"
echo
echo "    Sandboxing note: Tml only supports AppArmor, turned on or off"
echo "    from Preferences inside the app (not a flag here). On"
echo "    Debian/Ubuntu, AppArmor is your system's active LSM by default,"
echo "    so a loaded profile is one the kernel actually enforces. On"
echo "    distros where AppArmor isn't the active LSM (e.g. Fedora's"
echo "    SELinux default), a loaded profile sits unused and Tml launches"
echo "    unsandboxed - the app says so plainly rather than pretending"
echo "    otherwise."
