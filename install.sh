#!/bin/sh
set -eu

usage() {
  cat <<EOF
usage: $0 [--nightly]

Download Striem and install it for this user. Linux, no sudo.

  --nightly    the rolling build from next, instead of the stable release
  -h, --help   show this help

Quit Striem first: a running copy keeps the old version.
EOF
}

RELEASES=https://github.com/alen-androsevic/striem/releases

case ${1-} in
  '')
    file=striem.flatpak
    url=$RELEASES/latest/download/striem.flatpak
    ;;
  --nightly)
    file=striem-nightly.flatpak
    url=$RELEASES/download/nightly-rolling/striem-nightly.flatpak
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

# Both links always point at the current build, so this script never needs
# editing when a release goes out.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "Downloading $file…"
curl -fL# -o "$tmp/$file" "$url"

# The bundle carries its runtime's origin, so flatpak adds the Flathub remote
# itself if this machine has none. Both channels share one app ID, so this
# replaces whichever one is already installed.
flatpak install --user -y "$tmp/$file"

echo
echo "Installed. Open Striem from the app menu, or run:"
echo "  flatpak run io.github.striem.Striem"
