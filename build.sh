#!/bin/sh
# Build and install Striem as a user Flatpak (Bazzite / any Flatpak system). No sudo needed.
set -eu
cd "$(dirname "$0")"

flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

if ! flatpak info org.flatpak.Builder >/dev/null 2>&1; then
  flatpak install --user -y flathub org.flatpak.Builder
fi

flatpak run org.flatpak.Builder --user --install --install-deps-from=flathub --force-clean \
  build-dir flatpak/io.github.striem.Striem.yml

echo
echo "Installed. Open Striem from the app menu, or run: flatpak run io.github.striem.Striem"
