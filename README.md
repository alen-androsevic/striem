# Striem

Watch the RTSP camera streams listed in a folder of `.xspf` playlists — all at once in a grid, or one at a time.

## Install (Bazzite / any Flatpak system)

Flatpak is Linux-only; there is no macOS build path.

Install a bundle someone handed you:

```sh
flatpak install --user striem.flatpak
```

Or build it from source:

```sh
./build.sh
```

The first build downloads the KDE runtime and compiles libmpv, so it takes a while; later builds reuse the cache. Without git, fetch the source as a tarball — `refs/heads/main` pins the branch regardless of the repo's default:

```sh
curl -L https://github.com/alen-androsevic/striem/archive/refs/heads/main.tar.gz | tar xz
cd striem-main && ./build.sh
```

To update, install a newer bundle or rebuild: either one replaces the installed copy in place. Quit Striem first, since a running instance keeps the old version alive. `flatpak update` does nothing for Striem — a locally installed app has no remote to update from.

## Hand it to someone else

```sh
./build.sh --bundle
```

This writes `striem.flatpak`, a single file that needs no source checkout and no build toolchain on their machine. Build it on the architecture they run (x86_64 for a Bazzite PC) — a bundle will not install on a different one.

Or let CI build it, which is the only option if you have no Linux machine:

```sh
git tag v0.1.1 && git push origin v0.1.1
```

GitHub Actions builds the x86_64 bundle and attaches it to a release, so they can download `striem.flatpak` from the Releases page. Every push to `main` builds one too, downloadable from that run's Artifacts.

## Use

Put your `.xspf` playlists in `~/Videos/Cameras`, or pick another folder with **Choose folder…**. The app rescans when files in the folder change.

| Action | How |
|---|---|
| Focus a camera | Click its tile, its toolbar button, or press `1`–`9` |
| Back to the grid | `Esc`, `0`, **All**, or click the focused camera |
| Sound | 🔇/🔊 on a tile. Only one camera plays sound at a time; focusing a camera gives it the sound, and returning to the grid silences it |
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
