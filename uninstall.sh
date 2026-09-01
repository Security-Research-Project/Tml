#!/usr/bin/env bash
set -euo pipefail

PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

echo "==> Removing AppArmor profiles (if any were loaded)..."
for p in /etc/apparmor.d/tml.*; do
    [ -e "$p" ] || continue
    sudo apparmor_parser -R "$p" 2>/dev/null || true
    sudo rm -f "$p"
done

echo "==> Removing desktop entry and icon..."
rm -f "${HOME}/.local/share/applications/org.tml.Tml.desktop"
rm -f "${HOME}/.local/share/icons/hicolor/scalable/apps/org.tml.Tml.svg"
rm -f "${HOME}/.local/share/icons/hicolor/symbolic/apps/org.tml.Tml-symbolic.svg"
gtk-update-icon-cache "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true

echo "==> Uninstalling the tml Python package..."
python3 -m pip uninstall -y tml || true

if $PURGE; then
    echo "==> --purge given: removing installed browsers and all Tml data..."
    rm -rf "${HOME}/.config/tml" "${HOME}/.cache/tml" "${HOME}/.local/share/tml"
else
    echo "==> Browsers installed under ~/.local/share/tml/browsers were left in place."
    echo "    Re-run with --purge to remove everything, including installed browsers."
fi

echo "==> Done."
