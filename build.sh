#!/bin/sh
set -eu

usage() {
  cat <<EOF
usage: $0 [--bundle]

Build Striem as a Flatpak. Linux, no sudo.

  (no option)  build and install it for this user
  --bundle     write striem.flatpak, one file to share
  -h, --help   show this help

A bundle only installs on the CPU architecture it was built on.
EOF
}

mode=${1-}
case "$mode" in
  '' | --bundle) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

cd "$(dirname "$0")"

APP_ID=io.github.striem.Striem
MANIFEST=flatpak/io.github.striem.Striem.yml
FLATHUB=https://dl.flathub.org/repo/flathub.flatpakrepo

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
