# Striem

Watch the RTSP camera streams listed in a folder of `.xspf` playlists — all at once in a grid, or one at a time.

## Install (Bazzite / any Flatpak system)

```sh
./build.sh
```

The first build downloads the KDE runtime and compiles libmpv, so it takes a while. Later builds are faster.

## Use

Put your `.xspf` playlists in `~/Videos/Cameras`, or pick another folder with **Choose folder…**. The app rescans when files in the folder change.

| Action | How |
|---|---|
| Focus a camera | Click its tile, its toolbar button, or press `1`–`9` |
| Back to the grid | `Esc`, `0`, **All**, or click the focused camera |
| Sound | 🔇/🔊 on a tile. Only one camera plays sound at a time; focusing a camera gives it the sound |
| Mute / unmute | `M` or **Mute** |
| Fullscreen | `F11` |

## Develop (macOS or Linux)

```sh
brew install mpv ffmpeg mediamtx      # or your distro's packages
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Fake cameras for manual testing:

```sh
/opt/homebrew/opt/mediamtx/bin/mediamtx /opt/homebrew/etc/mediamtx/mediamtx.yml &
scripts/fakecams.sh &      # rtsp://127.0.0.1:8554/cam1 … cam4
.venv/bin/python -m striem
```

`scripts/snapshot.py` drives the window with scripted steps and saves screenshots. See its docstring.
