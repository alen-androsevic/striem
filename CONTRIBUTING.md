# Contributing

## Set up

Striem is Python, Qt (PySide6) and libmpv. Develop on Linux or macOS:

```sh
brew install mpv ffmpeg mediamtx        # or your distro's packages
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

## Run it against fake cameras

```sh
mediamtx scripts/mediamtx.yml &   # RTSP server on :8554
scripts/fakecams.sh &             # publishes rtsp://127.0.0.1:8554/cam1 … cam4
.venv/bin/python -m striem
```

Point **⋮ → Choose folder…** at a folder of `.xspf` playlists for those URLs.

`scripts/snapshot.py` drives the window with scripted steps and saves screenshots, which is how UI changes get checked. Its docstring lists the steps.

## Tests

Logic lives in Qt-free modules (`playlist`, `layout`, `audio`, `capture`) and is unit-tested. Tests never create Qt widgets, so check anything on screen against the fake cameras.

## Branches

1. Branch off `next`, and open your pull request against `next`.
2. Every merge into `next` publishes the [nightly build](https://github.com/alen-androsevic/striem/releases/tag/nightly-rolling).
3. `next` is merged into `main` to release.

Pull requests run the tests. The Flatpak is built only for `next` and release tags.

## Build the Flatpak

Linux only:

```sh
./build.sh              # build and install for this user
./build.sh --bundle     # write striem.flatpak to share
```

A bundle only installs on the CPU architecture it was built on.

## Release

1. Bump the version in `pyproject.toml`, `striem/__init__.py` and `flatpak/io.github.striem.Striem.metainfo.xml` — a test keeps them in step.
2. Merge `next` into `main`.
3. Tag `main` and push the tag. CI builds the bundle and publishes the release.

```sh
git tag v0.1.5 && git push origin v0.1.5
```
