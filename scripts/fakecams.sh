#!/bin/sh
set -u

case ${1-} in
  -h | --help)
    cat <<EOF
usage: $0 [cam1 cam2 ...]

Publish fake RTSP cameras to rtsp://127.0.0.1:8554/<name>. Default: cam1 to cam4.

Start the server first:
  mediamtx scripts/mediamtx.yml &
EOF
    exit 0
    ;;
esac

src() {
  case "$1" in
    cam1) echo "testsrc=size=640x360:rate=25" ;;  # shows a running frame counter
    cam2) echo "smptehdbars=size=640x360:rate=25" ;;
    cam3) echo "cellauto=size=640x360:rate=25:rule=110:random_fill_ratio=0.5" ;;
    cam4) echo "life=size=640x360:rate=25:mold=10:ratio=0.5:death_color=#203040:life_color=#30c080" ;;
    *)    echo "rgbtestsrc=size=640x360:rate=25" ;;
  esac
}
[ $# -eq 0 ] && set -- cam1 cam2 cam3 cam4
n=0
for cam in "$@"; do
  n=$((n + 1))
  ffmpeg -loglevel error -re -f lavfi -i "$(src "$cam")" -f lavfi -i "sine=frequency=$((220 * n))" \
    -pix_fmt yuv420p -c:v libx264 -preset ultrafast -tune zerolatency -g 25 -c:a aac \
    -f rtsp "rtsp://127.0.0.1:8554/$cam" &
done
wait
