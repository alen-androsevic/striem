#!/bin/sh
# Build Striem as a Flatpak. Linux only (Flatpak does not exist on macOS). No sudo needed.
#
#   ./build.sh            build and install it for the current user
#   ./build.sh --bundle   build and write striem.flatpak, one file to hand to someone else
#
# A bundle only runs on the architecture it was built on, so build it on a machine
# matching the target (x86_64 for Bazzite on a PC).
set -eu
cd "$(dirname "$0")"

APP_ID=io.github.striem.Striem
MANIFEST=flatpak/io.github.striem.Striem.yml
FLATHUB=https://dl.flathub.org/repo/flathub.flatpakrepo

mode=${1-}
case "$mode" in
  '' | --bundle) ;;
  *)
    echo "usage: $0 [--bundle]" >&2
    exit 2
    ;;
esac

flatpak remote-add --user --if-not-exists flathub "$FLATHUB"

if ! flatpak info org.flatpak.Builder >/dev/null 2>&1; then
  flatpak install --user -y flathub org.flatpak.Builder
fi

if [ "$mode" = --bundle ]; then
  flatpak run org.flatpak.Builder --user --repo=repo --install-deps-from=flathub --force-clean \
    build-dir "$MANIFEST"

  # --runtime-repo records where the KDE runtime comes from, so installing the
  # bundle on a machine without the Flathub remote adds it instead of failing.
  flatpak build-bundle --runtime-repo="$FLATHUB" repo striem.flatpak "$APP_ID"

  echo
  echo "Wrote striem.flatpak ($(du -h striem.flatpak | cut -f1))."
  echo "On the other machine: flatpak install --user striem.flatpak"
else
  flatpak run org.flatpak.Builder --user --install --install-deps-from=flathub --force-clean \
    build-dir "$MANIFEST"

  echo
  echo "Installed. Open Striem from the app menu, or run: flatpak run $APP_ID"
fi
