# Striem Camera Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Flatpak desktop app for Bazzite that reads every `.xspf` playlist in a folder and shows the RTSP camera streams in an auto-sized grid, with click-to-focus and at most one camera unmuted.

**Architecture:** Pure-Python core (`playlist.py`, `layout.py`, `audio.py`, no Qt) holds all decisions and is unit-tested. A Qt layer (`player.py` → `tile.py` → `window.py`) draws each stream with libmpv's OpenGL render API inside a `QOpenGLWidget`. Packaging is a Flatpak manifest on the KDE 6.11 runtime + PySide BaseApp that builds libmpv from source.

**Tech Stack:** Python ≥ 3.11, PySide6 (Qt 6), python-mpv (`mpv` on PyPI) 1.0.8, libmpv 0.41.0, pytest, Flatpak (org.kde.Platform 6.11, io.qt.PySide.BaseApp 6.11).

**Spec:** `docs/superpowers/specs/2026-09-11-striem-camera-viewer-design.md`

## Global Constraints

- App id: `io.github.striem.Striem`. Command: `striem`. Display name: `Striem`.
- `striem/playlist.py`, `striem/layout.py`, `striem/audio.py` must not import PySide6 or mpv.
- mpv options, exactly: `vo=libmpv`, `profile=low-latency`, `rtsp-transport=tcp`, `cache=no`, `hwdec=auto-copy-safe`, `keep-open=yes`, `mute=yes`.
- Reconnect backoff seconds: 2, 4, 8, 16, 30, 30, … reset to 2 once playback starts.
- Folder rescan debounce: 500 ms. Default folder: `~/Videos/Cameras`.
- Grid: 1→1×1, 2→2×1, 3–4→2×2, 5–6→3×2, 7–9→3×3, beyond `cols=ceil(sqrt(n))`, `rows=ceil(n/cols)`.
- Keys: `1`–`9` focus camera N, `Esc`/`0` back to grid, `M` mute toggle, `F11` fullscreen.
- Stream URLs carry no credentials; log and display them as-is.
- Flatpak `finish-args`, exactly: `--share=ipc`, `--share=network`, `--socket=wayland`, `--socket=fallback-x11`, `--device=dri`, `--socket=pulseaudio`, `--filesystem=home:ro`.
- Commit messages: short imperative subject, no attribution/co-author lines.
- Dev environment (macOS): repo venv at `.venv`, Homebrew `mpv` (provides `/opt/homebrew/lib/libmpv.dylib`), `ffmpeg`, `mediamtx`. Run tests with `.venv/bin/python -m pytest`.

## File Map

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, pytest config |
| `.gitignore` | Ignore venv, caches, Flatpak build dirs, screenshots |
| `striem/__init__.py` | Package marker |
| `striem/playlist.py` | `Camera`, `parse_playlist`, `load_cameras` |
| `striem/layout.py` | `grid_dims`, `diff_cameras` |
| `striem/audio.py` | `AudioState` — at most one camera audible |
| `striem/player.py` | libmpv lookup patch, `MPV_OPTIONS`, `MpvWidget` |
| `striem/tile.py` | `reconnect_delay`, `CameraTile` |
| `striem/settings.py` | `DEFAULT_FOLDER`, `Settings` (QSettings) |
| `striem/window.py` | `MainWindow` |
| `striem/__main__.py` | `create_app`, `main` |
| `scripts/fakecams.sh` | Publish fake RTSP cameras to a local mediamtx |
| `scripts/snapshot.py` | Drive the real window with scripted steps and save screenshots |
| `tests/test_playlist.py`, `tests/test_layout.py`, `tests/test_audio.py`, `tests/test_tile.py`, `tests/test_packaging.py` | Tests |
| `flatpak/io.github.striem.Striem.yml` | Flatpak manifest |
| `flatpak/striem.sh` | Launcher installed as `/app/bin/striem` |
| `flatpak/io.github.striem.Striem.desktop` / `.svg` / `.metainfo.xml` | Desktop integration |
| `build.sh` | One-command Flatpak build + install on Bazzite |
| `README.md` | Usage, keys, build, dev testing |

---

### Task 1: Scaffold + playlist parsing

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `striem/__init__.py`, `striem/playlist.py`
- Test: `tests/test_playlist.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Camera` — frozen dataclass `Camera(name: str, url: str, source: pathlib.Path)`
  - `parse_playlist(path: Path) -> list[Camera]` (raises `xml.etree.ElementTree.ParseError` / `OSError`)
  - `load_cameras(folder: Path) -> tuple[list[Camera], list[tuple[Path, str]]]` — never raises for bad files.

- [ ] **Step 1: Create project scaffold**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "striem"
version = "0.1.0"
description = "Watch the RTSP camera streams listed in a folder of .xspf playlists"
requires-python = ">=3.11"
dependencies = ["PySide6>=6.8", "mpv>=1.0.8"]

[project.optional-dependencies]
dev = ["pytest>=8", "PyYAML>=6"]

[project.scripts]
striem = "striem.__main__:main"

[tool.setuptools]
packages = ["striem"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
*.egg-info/
.flatpak-builder/
build-dir/
shots/
```

`striem/__init__.py`:
```python
"""Striem: watch the RTSP cameras listed in a folder of .xspf playlists."""
```

Run:
```bash
cd /Users/alen/code/striem && python3 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'
```
Expected: exits 0.

- [ ] **Step 2: Write the failing tests**

`tests/test_playlist.py`:
```python
from pathlib import Path

from striem.playlist import Camera, load_cameras, parse_playlist

VLC_PLAYLIST = """<?xml version="1.0" encoding="UTF-8"?>
<playlist xmlns="http://xspf.org/ns/0/" xmlns:vlc="http://www.videolan.org/vlc/playlist/ns/0/" version="1">
\t<title>Playlist</title>
\t<trackList>
\t\t<track>
\t\t\t<location>rtsp://192.168.1.20:554/stream1</location>
\t\t\t<title>Front door</title>
\t\t\t<duration>0</duration>
\t\t\t<extension application="http://www.videolan.org/vlc/playlist/0">
\t\t\t\t<vlc:id>0</vlc:id>
\t\t\t\t<vlc:option>network-caching=1000</vlc:option>
\t\t\t</extension>
\t\t</track>
\t</trackList>
\t<extension application="http://www.videolan.org/vlc/playlist/0">
\t\t<vlc:item tid="0"/>
\t</extension>
</playlist>
"""


def track(location=None, title=None):
    parts = ["<track>"]
    if location is not None:
        parts.append(f"<location>{location}</location>")
    if title is not None:
        parts.append(f"<title>{title}</title>")
    parts.append("</track>")
    return "".join(parts)


def playlist(*tracks, namespace=True):
    ns = ' xmlns="http://xspf.org/ns/0/"' if namespace else ""
    return f'<?xml version="1.0"?><playlist{ns} version="1"><trackList>{"".join(tracks)}</trackList></playlist>'


def write(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def test_vlc_playlist_gives_one_camera(tmp_path):
    path = write(tmp_path, "front.xspf", VLC_PLAYLIST)
    assert parse_playlist(path) == [Camera("Front door", "rtsp://192.168.1.20:554/stream1", path)]


def test_untitled_track_uses_file_stem(tmp_path):
    path = write(tmp_path, "garage.xspf", playlist(track("rtsp://h/garage")))
    assert [c.name for c in parse_playlist(path)] == ["garage"]


def test_several_tracks_in_one_file_keep_order(tmp_path):
    path = write(tmp_path, "house.xspf", playlist(track("rtsp://h/a", "Hall"), track("rtsp://h/b", "Attic")))
    assert [(c.name, c.url) for c in parse_playlist(path)] == [("Hall", "rtsp://h/a"), ("Attic", "rtsp://h/b")]


def test_several_untitled_tracks_are_numbered(tmp_path):
    path = write(tmp_path, "yard.xspf", playlist(track("rtsp://h/1"), track("rtsp://h/2")))
    assert [c.name for c in parse_playlist(path)] == ["yard", "yard 2"]


def test_track_without_location_is_skipped(tmp_path):
    path = write(tmp_path, "x.xspf", playlist(track(title="Nothing"), track("rtsp://h/ok", "Ok")))
    assert [c.name for c in parse_playlist(path)] == ["Ok"]


def test_whitespace_around_location_and_title_is_trimmed(tmp_path):
    path = write(tmp_path, "x.xspf", playlist(track("\n  rtsp://h/cam  \n", "  Porch ")))
    camera = parse_playlist(path)[0]
    assert (camera.name, camera.url) == ("Porch", "rtsp://h/cam")


def test_playlist_without_namespace_is_read(tmp_path):
    path = write(tmp_path, "plain.xspf", playlist(track("rtsp://h/plain", "Plain"), namespace=False))
    assert [c.url for c in parse_playlist(path)] == ["rtsp://h/plain"]


def test_xml_entities_in_url_are_decoded(tmp_path):
    path = write(tmp_path, "d.xspf", playlist(track("rtsp://h/cam/realmonitor?channel=1&amp;subtype=0")))
    assert parse_playlist(path)[0].url == "rtsp://h/cam/realmonitor?channel=1&subtype=0"


def test_percent_encoding_is_kept_as_written(tmp_path):
    path = write(tmp_path, "p.xspf", playlist(track("rtsp://h/my%20cam")))
    assert parse_playlist(path)[0].url == "rtsp://h/my%20cam"


def test_malformed_file_is_reported_and_others_still_load(tmp_path):
    bad = write(tmp_path, "a-broken.xspf", "<playlist><trackList>")
    write(tmp_path, "b-good.xspf", playlist(track("rtsp://h/good", "Good")))
    cameras, errors = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["Good"]
    assert [path for path, _ in errors] == [bad]
    assert errors[0][1]


def test_duplicate_url_across_files_is_kept_once_first_wins(tmp_path):
    write(tmp_path, "a.xspf", playlist(track("rtsp://h/same", "First")))
    write(tmp_path, "b.xspf", playlist(track("rtsp://h/same", "Second")))
    cameras, _ = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["First"]


def test_files_are_read_in_case_insensitive_name_order(tmp_path):
    write(tmp_path, "b.xspf", playlist(track("rtsp://h/b", "B")))
    write(tmp_path, "A.xspf", playlist(track("rtsp://h/a", "A")))
    write(tmp_path, "c.xspf", playlist(track("rtsp://h/c", "C")))
    cameras, _ = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["A", "B", "C"]


def test_only_xspf_files_are_read_and_extension_case_is_ignored(tmp_path):
    write(tmp_path, "CAM.XSPF", playlist(track("rtsp://h/upper", "Upper")))
    write(tmp_path, "notes.txt", playlist(track("rtsp://h/txt", "Txt")))
    write(tmp_path, "list.m3u", "rtsp://h/m3u\n")
    (tmp_path / "folder.xspf").mkdir()
    cameras, errors = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["Upper"]
    assert errors == []


def test_missing_folder_gives_nothing(tmp_path):
    assert load_cameras(tmp_path / "nope") == ([], [])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playlist.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'striem.playlist'`.

- [ ] **Step 4: Implement**

`striem/playlist.py`:
```python
"""Read camera streams from the .xspf playlists in a folder."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Camera:
    name: str
    url: str
    source: Path


def load_cameras(folder: Path) -> tuple[list[Camera], list[tuple[Path, str]]]:
    """All cameras from the folder's .xspf files, plus (file, message) for files that failed.

    Files are read in case-insensitive name order; a URL seen twice is kept once (first wins).
    """
    cameras: list[Camera] = []
    errors: list[tuple[Path, str]] = []
    if not folder.is_dir():
        return cameras, errors
    seen: set[str] = set()
    for path in playlist_files(folder):
        try:
            found = parse_playlist(path)
        except (ET.ParseError, OSError) as exc:
            errors.append((path, str(exc)))
            continue
        for camera in found:
            if camera.url not in seen:
                seen.add(camera.url)
                cameras.append(camera)
    return cameras, errors


def playlist_files(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.suffix.lower() == ".xspf" and p.is_file()]
    return sorted(files, key=lambda p: p.name.lower())


def parse_playlist(path: Path) -> list[Camera]:
    """One Camera per <track> with a <location>. Works with or without the XSPF namespace."""
    root = ET.parse(path).getroot()
    cameras: list[Camera] = []
    untitled = 0
    for track in (el for el in root.iter() if _local(el.tag) == "track"):
        url = _child_text(track, "location")
        if not url:
            continue
        name = _child_text(track, "title")
        if not name:
            untitled += 1
            name = path.stem if untitled == 1 else f"{path.stem} {untitled}"
        cameras.append(Camera(name=name, url=url, source=path))
    return cameras


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local(child.tag) == name and child.text:
            return child.text.strip()
    return ""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_playlist.py -v`
Expected: 14 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore striem/__init__.py striem/playlist.py tests/test_playlist.py
git commit -m "Add project scaffold and xspf playlist parsing"
```

---

### Task 2: Grid sizing and camera diffing

**Files:**
- Create: `striem/layout.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `striem.playlist.Camera` (only its `.url`).
- Produces:
  - `grid_dims(n: int) -> tuple[int, int]` returning `(cols, rows)`
  - `diff_cameras(old: Sequence[Camera], new: Sequence[Camera]) -> tuple[list[Camera], list[Camera], list[Camera]]` returning `(added, removed, kept)`; `added` and `kept` hold the *new* Camera objects in new order, `removed` holds old objects in old order. Identity is the URL.

- [ ] **Step 1: Write the failing tests**

`tests/test_layout.py`:
```python
from pathlib import Path

import pytest

from striem.layout import diff_cameras, grid_dims
from striem.playlist import Camera


def cam(name, url):
    return Camera(name, url, Path(f"{name}.xspf"))


@pytest.mark.parametrize(
    "n, dims",
    [(0, (0, 0)), (1, (1, 1)), (2, (2, 1)), (3, (2, 2)), (4, (2, 2)), (5, (3, 2)),
     (6, (3, 2)), (7, (3, 3)), (9, (3, 3)), (10, (4, 3)), (13, (4, 4))],
)
def test_grid_dims(n, dims):
    assert grid_dims(n) == dims


def test_diff_splits_added_removed_kept():
    a, b, c = cam("a", "rtsp://a"), cam("b", "rtsp://b"), cam("c", "rtsp://c")
    added, removed, kept = diff_cameras([a, b], [b, c])
    assert added == [c]
    assert removed == [a]
    assert kept == [b]


def test_diff_keeps_camera_whose_title_changed_and_returns_new_object():
    old = cam("Old name", "rtsp://x")
    new = cam("New name", "rtsp://x")
    added, removed, kept = diff_cameras([old], [new])
    assert (added, removed) == ([], [])
    assert kept[0].name == "New name"


def test_diff_orders_follow_their_lists():
    a, b, c, d = (cam(n, f"rtsp://{n}") for n in "abcd")
    added, removed, _ = diff_cameras([d, c], [b, a])
    assert added == [b, a]
    assert removed == [d, c]


def test_diff_from_empty_adds_everything():
    a, b = cam("a", "rtsp://a"), cam("b", "rtsp://b")
    assert diff_cameras([], [a, b]) == ([a, b], [], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_layout.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'striem.layout'`.

- [ ] **Step 3: Implement**

`striem/layout.py`:
```python
"""Grid sizing and working out which camera tiles change after a rescan."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from striem.playlist import Camera


def grid_dims(n: int) -> tuple[int, int]:
    """(cols, rows) for n tiles: as square as possible, wider than tall."""
    if n <= 0:
        return 0, 0
    cols = math.ceil(math.sqrt(n))
    return cols, math.ceil(n / cols)


def diff_cameras(
    old: Sequence[Camera], new: Sequence[Camera]
) -> tuple[list[Camera], list[Camera], list[Camera]]:
    """(added, removed, kept), matched by URL. kept holds the new objects so renamed titles show."""
    old_urls = {c.url for c in old}
    new_urls = {c.url for c in new}
    added = [c for c in new if c.url not in old_urls]
    removed = [c for c in old if c.url not in new_urls]
    kept = [c for c in new if c.url in old_urls]
    return added, removed, kept
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_layout.py -v`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add striem/layout.py tests/test_layout.py
git commit -m "Add grid sizing and camera diffing"
```

---

### Task 3: One-unmuted-camera audio rule

**Files:**
- Create: `striem/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: nothing. Cameras are identified by URL string.
- Produces: class `AudioState` with attributes `active: str | None`, `muted: bool` and methods `is_unmuted(url: str | None) -> bool`, `toggle(url: str) -> None`, `focus(url: str) -> None`, `toggle_mute() -> None`, `forget(url: str) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_audio.py`:
```python
from striem.audio import AudioState

A, B = "rtsp://a", "rtsp://b"


def audible(state, *urls):
    return [u for u in urls if state.is_unmuted(u)]


def test_nothing_audible_at_start():
    assert audible(AudioState(), A, B) == []


def test_toggle_unmutes_camera():
    s = AudioState()
    s.toggle(A)
    assert audible(s, A, B) == [A]


def test_toggle_other_camera_moves_sound():
    s = AudioState()
    s.toggle(A)
    s.toggle(B)
    assert audible(s, A, B) == [B]


def test_toggle_audible_camera_silences_everything():
    s = AudioState()
    s.toggle(A)
    s.toggle(A)
    assert audible(s, A, B) == []
    assert s.active is None


def test_focus_makes_camera_audible_even_when_muted():
    s = AudioState()
    s.toggle(A)
    s.toggle_mute()
    s.focus(B)
    assert audible(s, A, B) == [B]
    assert s.muted is False


def test_mute_silences_and_restores_same_camera():
    s = AudioState()
    s.toggle(A)
    s.toggle_mute()
    assert audible(s, A, B) == []
    s.toggle_mute()
    assert audible(s, A, B) == [A]


def test_mute_without_active_camera_does_nothing():
    s = AudioState()
    s.toggle_mute()
    assert s.muted is False


def test_toggle_on_active_but_muted_camera_unmutes_it():
    s = AudioState()
    s.toggle(A)
    s.toggle_mute()
    s.toggle(A)
    assert audible(s, A, B) == [A]


def test_forget_active_camera_clears_it():
    s = AudioState()
    s.toggle(A)
    s.forget(A)
    assert s.active is None
    assert audible(s, A, B) == []


def test_forget_other_camera_changes_nothing():
    s = AudioState()
    s.toggle(A)
    s.forget(B)
    assert audible(s, A, B) == [A]


def test_none_is_never_audible():
    s = AudioState()
    assert s.is_unmuted(None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_audio.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'striem.audio'`.

- [ ] **Step 3: Implement**

`striem/audio.py`:
```python
"""Which camera is audible: at most one at a time, anywhere in the app."""

from __future__ import annotations


class AudioState:
    """A camera (by URL) is audible iff it is `active` and `muted` is off."""

    def __init__(self) -> None:
        self.active: str | None = None
        self.muted = False

    def is_unmuted(self, url: str | None) -> bool:
        return url is not None and url == self.active and not self.muted

    def toggle(self, url: str) -> None:
        """Tile speaker button: silence this camera if audible, else make it the audible one."""
        if self.is_unmuted(url):
            self.active = None
        else:
            self.active = url
            self.muted = False

    def focus(self, url: str) -> None:
        self.active = url
        self.muted = False

    def toggle_mute(self) -> None:
        """The M key: mute/unmute the remembered camera. No-op without one."""
        if self.active is not None:
            self.muted = not self.muted

    def forget(self, url: str) -> None:
        """The camera left the folder."""
        if self.active == url:
            self.active = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_audio.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add striem/audio.py tests/test_audio.py
git commit -m "Add one-unmuted-camera audio state"
```

---

### Task 4: mpv video widget and camera tile

**Files:**
- Create: `striem/player.py`, `striem/tile.py`, `scripts/fakecams.sh`
- Test: `tests/test_tile.py`

**Interfaces:**
- Consumes: `striem.playlist.Camera`.
- Produces:
  - `striem.player.MPV_OPTIONS: dict[str, str]`
  - `striem.player.MpvWidget(QOpenGLWidget)`: `play(url: str)`, `set_muted(muted: bool)`, `shutdown()`; signals `playing()`, `failed(str)`. Both signals are always delivered on the GUI thread.
  - `striem.tile.reconnect_delay(attempt: int) -> int`
  - `striem.tile.CameraTile(QWidget)`: `__init__(camera, parent=None)`, attribute `camera`, attribute `audible: bool`, `set_camera(camera)`, `set_audible(audible: bool)`, `status_text() -> str` (empty when no overlay shown), `shutdown()`; signals `clicked(object)` and `audioClicked(object)` carrying the tile's `Camera`.

Facts verified by spike (mpv 0.41, python-mpv 1.0.8, PySide6 6.11 on macOS):
- `QSurfaceFormat` 3.3 core must be set before `QApplication` exists (done in Task 5's `create_app`).
- The render context must be freed while the widget's GL context is current, *then* `player.terminate()`; otherwise the process segfaults on exit.
- A live stream that drops sets property `eof-reached` to `True` (no `end-file`); an unreachable stream gives `end-file` with `reason == b"error"`; a successful start gives `playback-restart`. Calling `play()` again on a running player first emits `end-file` with `reason == b"stop"` — ignore it.

- [ ] **Step 1: Add the fake camera script (dev tool used for verification)**

`scripts/fakecams.sh`:
```sh
#!/bin/sh
# Publish fake RTSP cameras to a local mediamtx on :8554.
# Usage: scripts/fakecams.sh [cam1 cam2 ...]   (default: cam1..cam4)
# Start mediamtx first:
#   /opt/homebrew/opt/mediamtx/bin/mediamtx /opt/homebrew/etc/mediamtx/mediamtx.yml
set -u
src() {
  case "$1" in
    cam1) echo "testsrc=size=640x360:rate=25" ;;  # shows a running frame counter
    cam2) echo "smptehdbars=size=640x360:rate=25" ;;
    cam3) echo "mandelbrot=size=640x360:rate=25" ;;
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
```
Run: `chmod +x scripts/fakecams.sh`

- [ ] **Step 2: Write the failing test**

`tests/test_tile.py`:
```python
import pytest

from striem.player import MPV_OPTIONS
from striem.tile import reconnect_delay


@pytest.mark.parametrize("attempt, seconds", [(0, 2), (1, 4), (2, 8), (3, 16), (4, 30), (5, 30), (50, 30)])
def test_reconnect_backoff(attempt, seconds):
    assert reconnect_delay(attempt) == seconds


def test_mpv_options_match_spec():
    assert MPV_OPTIONS == {
        "vo": "libmpv",
        "profile": "low-latency",
        "rtsp_transport": "tcp",
        "cache": "no",
        "hwdec": "auto-copy-safe",
        "keep_open": "yes",
        "mute": "yes",
    }
```
(python-mpv turns `_` in option names into `-`.)

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_tile.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'striem.player'`.

- [ ] **Step 4: Implement `striem/player.py`**

```python
"""One mpv player drawn inside a Qt widget through libmpv's OpenGL render API.

Wayland does not let mpv draw into another app's window (--wid), so mpv renders
into the QOpenGLWidget's framebuffer instead.
"""

from __future__ import annotations

import ctypes.util
import os

from PySide6.QtCore import Signal
from PySide6.QtGui import QOpenGLContext
from PySide6.QtOpenGLWidgets import QOpenGLWidget

_LIBMPV_CANDIDATES = ("/app/lib/libmpv.so.2", "/opt/homebrew/lib/libmpv.dylib")


def _point_python_mpv_at_libmpv() -> None:
    """python-mpv loads libmpv via ctypes.util.find_library('mpv'), which misses the
    Flatpak (/app/lib) and Homebrew locations; answer that lookup ourselves."""
    path = next((p for p in _LIBMPV_CANDIDATES if os.path.exists(p)), None)
    if path is None:
        return
    original = ctypes.util.find_library
    ctypes.util.find_library = lambda name: path if name == "mpv" else original(name)


_point_python_mpv_at_libmpv()
import mpv  # noqa: E402  (must come after the lookup patch)

MPV_OPTIONS = {
    "vo": "libmpv",
    "profile": "low-latency",
    "rtsp_transport": "tcp",
    "cache": "no",
    "hwdec": "auto-copy-safe",
    "keep_open": "yes",
    "mute": "yes",
}


def _get_proc_address(_ctx, name: bytes) -> int:
    context = QOpenGLContext.currentContext()
    address = context.getProcAddress(name.decode()) if context else 0
    return int(address) if address else 0


# Module level so the ctypes callback outlives every render context.
_GET_PROC_ADDRESS = mpv.MpvGlGetProcAddressFn(_get_proc_address)


class MpvWidget(QOpenGLWidget):
    """Plays one URL. `playing` and `failed` are always emitted on the GUI thread."""

    playing = Signal()
    failed = Signal(str)
    _frame_ready = Signal()
    _from_mpv = Signal(str, str)  # (kind, detail), marshalled off mpv's event thread

    def __init__(self, parent=None):
        super().__init__(parent)
        self._url: str | None = None
        self._render = None
        self._player = mpv.MPV(**MPV_OPTIONS)
        self._frame_ready.connect(self.update)
        self._from_mpv.connect(self._relay)
        self._player.register_event_callback(self._on_mpv_event)
        self._player.observe_property("eof-reached", self._on_eof)

    def play(self, url: str) -> None:
        """Start (or restart) the stream. Waits for the GL context if not shown yet."""
        self._url = url
        if self._render is not None and self._player is not None:
            self._player.play(url)

    def set_muted(self, muted: bool) -> None:
        if self._player is not None:
            self._player.mute = muted

    def shutdown(self) -> None:
        """Release mpv. Call before the widget is destroyed; safe to call twice."""
        if self._player is None:
            return
        if self._render is not None:
            self.makeCurrent()
            self._render.free()
            self._render = None
            self.doneCurrent()
        self._player.terminate()
        self._player = None

    # Qt OpenGL hooks

    def initializeGL(self) -> None:
        self._render = mpv.MpvRenderContext(
            self._player, "opengl", opengl_init_params={"get_proc_address": _GET_PROC_ADDRESS}
        )
        self._render.update_cb = self._frame_ready.emit
        if self._url:
            self._player.play(self._url)

    def paintGL(self) -> None:
        if self._render is None:
            return
        ratio = self.devicePixelRatio()
        self._render.render(
            flip_y=True,
            opengl_fbo={
                "w": round(self.width() * ratio),
                "h": round(self.height() * ratio),
                "fbo": self.defaultFramebufferObject(),
            },
        )

    # mpv event thread -> GUI thread

    def _on_mpv_event(self, event) -> None:
        data = event.as_dict()
        kind = data.get("event")
        if kind == b"playback-restart":
            self._from_mpv.emit("playing", "")
        elif kind == b"end-file" and data.get("reason") == b"error":
            detail = (data.get("file_error") or b"error").decode(errors="replace")
            self._from_mpv.emit("failed", detail)

    def _on_eof(self, _name, value) -> None:
        if value:
            self._from_mpv.emit("failed", "stream ended")

    def _relay(self, kind: str, detail: str) -> None:
        if kind == "playing":
            self.playing.emit()
        else:
            self.failed.emit(detail)
```

- [ ] **Step 5: Implement `striem/tile.py`**

```python
"""One camera in the grid: video, name label, status overlay and speaker button."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from striem.player import MpvWidget

RECONNECT_DELAYS = (2, 4, 8, 16, 30)

_OVERLAY_STYLE = (
    "color: white; background: rgba(0, 0, 0, 150); padding: 3px 8px; border-radius: 4px;"
)
_MARGIN = 8


def reconnect_delay(attempt: int) -> int:
    """Seconds to wait before reconnect attempt `attempt` (0-based)."""
    return RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]


class CameraTile(QWidget):
    clicked = Signal(object)  # Camera
    audioClicked = Signal(object)  # Camera

    def __init__(self, camera, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.audible = False
        self._attempt = 0
        self._countdown = 0

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("CameraTile { background: black; }")
        self.video = MpvWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video)

        self._name = QLabel(camera.name, self)
        self._name.setStyleSheet(_OVERLAY_STYLE)
        self._status = QLabel("Connecting…", self)
        self._status.setStyleSheet(_OVERLAY_STYLE)
        self._audio = QToolButton(self)
        self._audio.setText("🔇")
        self._audio.setToolTip("Play this camera's sound")
        self._audio.setStyleSheet(_OVERLAY_STYLE)
        self._audio.clicked.connect(lambda: self.audioClicked.emit(self.camera))

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self.video.playing.connect(self._on_playing)
        self.video.failed.connect(self._on_failed)
        self.video.play(camera.url)

    def set_camera(self, camera) -> None:
        """Same stream, possibly a new title."""
        self.camera = camera
        self._name.setText(camera.name)
        self._place_overlays()

    def set_audible(self, audible: bool) -> None:
        self.audible = audible
        self.video.set_muted(not audible)
        self._audio.setText("🔊" if audible else "🔇")

    def status_text(self) -> str:
        return self._status.text() if not self._status.isHidden() else ""

    def shutdown(self) -> None:
        self._timer.stop()
        self.video.shutdown()

    def _on_playing(self) -> None:
        self._attempt = 0
        self._timer.stop()
        self._status.hide()

    def _on_failed(self, _reason: str) -> None:
        if self._timer.isActive():
            return
        self._countdown = reconnect_delay(self._attempt)
        self._attempt += 1
        self._show_status(f"Reconnecting in {self._countdown} s")
        self._timer.start()

    def _tick(self) -> None:
        self._countdown -= 1
        if self._countdown > 0:
            self._show_status(f"Reconnecting in {self._countdown} s")
            return
        self._timer.stop()
        self._show_status("Connecting…")
        self.video.play(self.camera.url)

    def _show_status(self, text: str) -> None:
        self._status.setText(text)
        self._status.show()
        self._place_overlays()

    def _place_overlays(self) -> None:
        for label in (self._name, self._status, self._audio):
            label.adjustSize()
            label.raise_()
        self._name.move(_MARGIN, _MARGIN)
        self._audio.move(self.width() - self._audio.width() - _MARGIN, _MARGIN)
        self._status.move(
            (self.width() - self._status.width()) // 2, (self.height() - self._status.height()) // 2
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_overlays()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.camera)
        super().mousePressEvent(event)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -v`
Expected: all tests pass (playlist 14, layout 15, audio 11, tile 8).

- [ ] **Step 7: Smoke-check a tile against a fake camera**

Prerequisites (leave running in background shells): mediamtx (command in `scripts/fakecams.sh` header) and `scripts/fakecams.sh`.

Run:
```bash
.venv/bin/python - <<'EOF'
import locale, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
fmt = QSurfaceFormat(); fmt.setVersion(3, 3); fmt.setProfile(QSurfaceFormat.CoreProfile)
QSurfaceFormat.setDefaultFormat(fmt)
app = QApplication(sys.argv)
locale.setlocale(locale.LC_NUMERIC, "C")
from striem.playlist import Camera
from striem.tile import CameraTile
tile = CameraTile(Camera("Fake cam2", "rtsp://127.0.0.1:8554/cam2", Path("x.xspf")))
tile.resize(640, 360); tile.show()
def done():
    tile.grab().save("shots/tile.png"); print("status:", repr(tile.status_text()))
    tile.shutdown(); app.quit()
QTimer.singleShot(5000, done)
app.exec()
EOF
```
(run `mkdir -p shots` first)
Expected: prints `status: ''`, exit code 0, and `shots/tile.png` shows SMPTE colour bars with a "Fake cam2" label top-left and 🔇 top-right. View the PNG to confirm.

- [ ] **Step 8: Commit**

```bash
git add striem/player.py striem/tile.py scripts/fakecams.sh tests/test_tile.py
git commit -m "Add mpv video widget and camera tile with reconnect"
```

---

### Task 5: Main window, settings, entry point, snapshot tool

**Files:**
- Create: `striem/settings.py`, `striem/window.py`, `striem/__main__.py`, `scripts/snapshot.py`

**Interfaces:**
- Consumes: `load_cameras`, `Camera` (Task 1); `grid_dims`, `diff_cameras` (Task 2); `AudioState` (Task 3); `CameraTile` (Task 4).
- Produces:
  - `striem.settings.DEFAULT_FOLDER: Path`, `Settings` with `folder() -> Path`, `set_folder(folder: Path) -> None`
  - `striem.window.MainWindow(settings)` — `settings` is any object with `folder()`/`set_folder()`. Public methods: `rescan()`, `focus_index(i: int)` (0-based), `show_grid()`, `toggle_audio_index(i: int)` (0-based), `toggle_mute()`, `tiles() -> list[CameraTile]` (camera order).
  - `striem.__main__.create_app(argv: list[str]) -> QApplication`, `main() -> int`

- [ ] **Step 1: Implement `striem/settings.py`**

```python
"""Remember the chosen playlist folder between launches."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

DEFAULT_FOLDER = Path.home() / "Videos" / "Cameras"


class Settings:
    def __init__(self) -> None:
        self._store = QSettings("striem", "Striem")

    def folder(self) -> Path:
        value = self._store.value("folder", "")
        return Path(value) if value else DEFAULT_FOLDER

    def set_folder(self, folder: Path) -> None:
        self._store.setValue("folder", str(folder))
```

- [ ] **Step 2: Implement `striem/window.py`**

```python
"""Main window: camera grid, focus mode, toolbar, shortcuts and folder watching."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from striem.audio import AudioState
from striem.layout import diff_cameras, grid_dims
from striem.playlist import Camera, load_cameras
from striem.tile import CameraTile

RESCAN_DEBOUNCE_MS = 500


def _pretty(folder: Path) -> str:
    home = str(Path.home())
    text = str(folder)
    return "~" + text[len(home):] if text.startswith(home) else text


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("Striem")
        self.resize(1280, 760)
        self._settings = settings
        self._folder: Path = settings.folder()
        self._cameras: list[Camera] = []
        self._tiles: dict[str, CameraTile] = {}
        self._focused: str | None = None
        self._audio = AudioState()
        self._camera_actions: list[QAction] = []

        self._build_toolbar()
        self._build_pages()
        self._build_shortcuts()

        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(RESCAN_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.rescan)
        self._watcher.directoryChanged.connect(self._debounce.start)
        self._watcher.fileChanged.connect(self._debounce.start)

        self.rescan()

    # Public API (also used by scripts/snapshot.py)

    def rescan(self) -> None:
        cameras, errors = load_cameras(self._folder)
        added, removed, kept = diff_cameras(self._cameras, cameras)
        for camera in removed:
            tile = self._tiles.pop(camera.url)
            self._audio.forget(camera.url)
            if self._focused == camera.url:
                self._focused = None
            self._grid.removeWidget(tile)
            tile.shutdown()
            tile.deleteLater()
        for camera in kept:
            self._tiles[camera.url].set_camera(camera)
        for camera in added:
            tile = CameraTile(camera, self._grid_page)
            tile.clicked.connect(self._on_tile_clicked)
            tile.audioClicked.connect(self._on_audio_clicked)
            self._tiles[camera.url] = tile
        self._cameras = cameras
        self._watch_folder()
        self._rebuild_camera_actions()
        self._relayout()
        self._apply_audio()
        self._show_errors(errors)

    def focus_index(self, index: int) -> None:
        if 0 <= index < len(self._cameras):
            self._focus(self._cameras[index].url)

    def show_grid(self) -> None:
        self._focused = None
        self._relayout()

    def toggle_audio_index(self, index: int) -> None:
        if 0 <= index < len(self._cameras):
            self._audio.toggle(self._cameras[index].url)
            self._apply_audio()

    def toggle_mute(self) -> None:
        self._audio.toggle_mute()
        self._apply_audio()

    def tiles(self) -> list[CameraTile]:
        return [self._tiles[c.url] for c in self._cameras]

    # Building the UI

    def _build_toolbar(self) -> None:
        self._toolbar = QToolBar("Cameras", self)
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)
        self._all_action = QAction("All", self)
        self._all_action.triggered.connect(self.show_grid)
        self._mute_action = QAction("Mute", self)
        self._mute_action.setCheckable(True)
        self._mute_action.triggered.connect(self.toggle_mute)
        self._folder_action = QAction("Choose folder…", self)
        self._folder_action.triggered.connect(self._choose_folder)
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._toolbar.addAction(self._all_action)
        self._camera_anchor = self._toolbar.addSeparator()
        self._toolbar.addWidget(spacer)
        self._toolbar.addAction(self._mute_action)
        self._toolbar.addAction(self._folder_action)

    def _build_pages(self) -> None:
        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        self._grid_page = QWidget(self._stack)
        self._grid_page.setStyleSheet("background: #111;")
        self._grid = QGridLayout(self._grid_page)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(2)
        self._stack.addWidget(self._grid_page)

        self._empty_page = QWidget(self._stack)
        empty_layout = QVBoxLayout(self._empty_page)
        empty_layout.addStretch()
        self._empty_label = QLabel(self._empty_page)
        empty_layout.addWidget(self._empty_label, alignment=Qt.AlignCenter)
        choose = QPushButton("Choose folder…", self._empty_page)
        choose.clicked.connect(self._choose_folder)
        empty_layout.addWidget(choose, alignment=Qt.AlignCenter)
        empty_layout.addStretch()
        self._stack.addWidget(self._empty_page)

    def _build_shortcuts(self) -> None:
        for number in range(1, 10):
            QShortcut(QKeySequence(str(number)), self, activated=lambda i=number - 1: self.focus_index(i))
        QShortcut(QKeySequence("0"), self, activated=self.show_grid)
        QShortcut(QKeySequence("Esc"), self, activated=self.show_grid)
        QShortcut(QKeySequence("M"), self, activated=self.toggle_mute)
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)

    # Keeping the UI in sync

    def _rebuild_camera_actions(self) -> None:
        for action in self._camera_actions:
            self._toolbar.removeAction(action)
            action.deleteLater()
        self._camera_actions = []
        for index, camera in enumerate(self._cameras):
            action = QAction(camera.name, self)
            if index < 9:
                action.setToolTip(f"{camera.name} (key {index + 1})")
            action.triggered.connect(lambda _=False, url=camera.url: self._focus(url))
            self._toolbar.insertAction(self._camera_anchor, action)
            self._camera_actions.append(action)

    def _relayout(self) -> None:
        grid = self._grid
        while grid.count():
            grid.takeAt(0)
        for row in range(grid.rowCount()):
            grid.setRowStretch(row, 0)
        for col in range(grid.columnCount()):
            grid.setColumnStretch(col, 0)

        if not self._cameras:
            self._empty_label.setText(f"No .xspf playlists in {_pretty(self._folder)}")
            self._stack.setCurrentWidget(self._empty_page)
            return
        self._stack.setCurrentWidget(self._grid_page)

        if self._focused is not None:
            # Hide the others instead of reparenting: moving a QOpenGLWidget recreates its GL context.
            for url, tile in self._tiles.items():
                tile.setVisible(url == self._focused)
            grid.addWidget(self._tiles[self._focused], 0, 0)
            grid.setRowStretch(0, 1)
            grid.setColumnStretch(0, 1)
            return

        cols, rows = grid_dims(len(self._cameras))
        for index, camera in enumerate(self._cameras):
            tile = self._tiles[camera.url]
            grid.addWidget(tile, index // cols, index % cols)
            tile.show()
        for row in range(rows):
            grid.setRowStretch(row, 1)
        for col in range(cols):
            grid.setColumnStretch(col, 1)

    def _apply_audio(self) -> None:
        for url, tile in self._tiles.items():
            tile.set_audible(self._audio.is_unmuted(url))
        self._mute_action.setChecked(self._audio.muted)

    def _show_errors(self, errors: list[tuple[Path, str]]) -> None:
        if errors:
            names = ", ".join(path.name for path, _ in errors)
            self.statusBar().showMessage(f"Could not read: {names}")
        else:
            self.statusBar().clearMessage()

    def _watch_folder(self) -> None:
        watched = self._watcher.directories() + self._watcher.files()
        if watched:
            self._watcher.removePaths(watched)
        if self._folder.is_dir():
            self._watcher.addPath(str(self._folder))
            files = [str(p) for p in self._folder.iterdir() if p.suffix.lower() == ".xspf"]
            if files:
                self._watcher.addPaths(files)

    # Reacting to the user

    def _focus(self, url: str) -> None:
        self._focused = url
        self._audio.focus(url)
        self._relayout()
        self._apply_audio()

    def _on_tile_clicked(self, camera: Camera) -> None:
        if self._focused == camera.url:
            self.show_grid()
        else:
            self._focus(camera.url)

    def _on_audio_clicked(self, camera: Camera) -> None:
        self._audio.toggle(camera.url)
        self._apply_audio()

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose camera playlist folder", str(self._folder))
        if not chosen:
            return
        self._folder = Path(chosen)
        self._settings.set_folder(self._folder)
        self._focused = None
        self.rescan()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event) -> None:
        for tile in self._tiles.values():
            tile.shutdown()
        super().closeEvent(event)
```

- [ ] **Step 3: Implement `striem/__main__.py`**

```python
"""Entry point: `striem` or `python -m striem`."""

from __future__ import annotations

import locale
import sys

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication


def create_app(argv: list[str]) -> QApplication:
    # Must happen before QApplication exists; libmpv's GL renderer wants a core profile.
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(argv)
    app.setApplicationName("Striem")
    app.setDesktopFileName("io.github.striem.Striem")
    # Qt resets the C locale; libmpv requires LC_NUMERIC=C.
    locale.setlocale(locale.LC_NUMERIC, "C")
    return app


def main() -> int:
    app = create_app(sys.argv)
    from striem.settings import Settings
    from striem.window import MainWindow

    window = MainWindow(Settings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Implement `scripts/snapshot.py`**

```python
"""Dev tool: run Striem on a folder, drive it with scripted steps, save screenshots.

Usage: .venv/bin/python scripts/snapshot.py --folder DIR --out DIR STEP...
Steps: wait:SECONDS  shot:NAME  focus:N  grid  audio:N  mute  state   (N is 1-based)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from striem.__main__ import create_app  # noqa: E402


class FixedFolder:
    def __init__(self, folder: Path):
        self._folder = folder

    def folder(self) -> Path:
        return self._folder

    def set_folder(self, folder: Path) -> None:
        self._folder = folder


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("steps", nargs="+")
    args = parser.parse_args()

    app = create_app(sys.argv[:1])
    from striem.window import MainWindow

    window = MainWindow(FixedFolder(args.folder))
    window.show()
    args.out.mkdir(parents=True, exist_ok=True)
    steps = list(args.steps)

    def run_next() -> None:
        if not steps:
            window.close()
            app.quit()
            return
        step = steps.pop(0)
        command, _, arg = step.partition(":")
        delay_ms = 0
        if command == "wait":
            delay_ms = int(float(arg) * 1000)
        elif command == "shot":
            path = args.out / f"{arg}.png"
            window.grab().save(str(path))
            print("saved", path, flush=True)
        elif command == "focus":
            window.focus_index(int(arg) - 1)
        elif command == "grid":
            window.show_grid()
        elif command == "audio":
            window.toggle_audio_index(int(arg) - 1)
        elif command == "mute":
            window.toggle_mute()
        elif command == "state":
            for tile in window.tiles():
                print(
                    f"{tile.camera.name}: audible={tile.audible} visible={tile.isVisible()} "
                    f"status={tile.status_text()!r}",
                    flush=True,
                )
        else:
            raise SystemExit(f"unknown step: {step}")
        QTimer.singleShot(delay_ms, run_next)

    QTimer.singleShot(0, run_next)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Verify grid, focus and audio against fake cameras**

Prerequisites: mediamtx and `scripts/fakecams.sh` running. Create playlists:
```bash
mkdir -p shots/cams && for i in 1 2 3 4; do cat > shots/cams/cam$i.xspf <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<playlist xmlns="http://xspf.org/ns/0/" version="1"><trackList><track><location>rtsp://127.0.0.1:8554/cam$i</location><title>Camera $i</title></track></trackList></playlist>
EOF
done
```
Run:
```bash
.venv/bin/python scripts/snapshot.py --folder shots/cams --out shots wait:6 shot:grid state audio:1 audio:3 state focus:2 wait:2 shot:focus state mute state grid wait:1 shot:back state
```
Expected output (order of lines as below; exit code 0):
- after first `state`: 4 lines, all `audible=False visible=True status=''`
- after `audio:1 audio:3`: only `Camera 3` has `audible=True`
- after `focus:2`: only `Camera 2` `audible=True visible=True`; others `visible=False`
- after `mute`: nobody audible
- after `grid`: all `visible=True`, nobody audible (mute still on)
View `shots/grid.png` (2×2 grid, four distinct patterns with labels), `shots/focus.png` (Camera 2 bars fill the window), `shots/back.png` (2×2 again).

- [ ] **Step 6: Run the unit tests**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add striem/settings.py striem/window.py striem/__main__.py scripts/snapshot.py
git commit -m "Add main window with grid, focus, audio, folder watching"
```

---

### Task 6: Flatpak packaging and build script

**Files:**
- Create: `flatpak/io.github.striem.Striem.yml`, `flatpak/striem.sh`, `flatpak/io.github.striem.Striem.desktop`, `flatpak/io.github.striem.Striem.svg`, `flatpak/io.github.striem.Striem.metainfo.xml`, `build.sh`, `README.md`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: package layout `striem/` and `python3 -m striem` from Task 5.
- Produces: `./build.sh` builds and installs `io.github.striem.Striem` for the current user.

Pinned sources (verified 2026-09-11 against Flathub/Haruna manifest and PyPI):
- libplacebo git `https://github.com/haasn/libplacebo.git` tag `v7.360.1` commit `cee9b076f2c63104ccfd497fa79c39a867293ec4`
- libass `https://github.com/libass/libass/releases/download/0.17.5/libass-0.17.5.tar.gz` sha256 `caab4b993dd7be6187c55623b789ed75dddefea6e65938af134637c732fe094a`
- mpv `https://github.com/mpv-player/mpv/archive/refs/tags/v0.41.0.tar.gz` sha256 `ee21092a5ee427353392360929dc64645c54479aefdb5babc5cfbb5fad626209`
- python-mpv wheel `https://files.pythonhosted.org/packages/f4/cf/0d5f52753366ecf2c3d763e331dcda54b0f20a1a8e52b175feb9c625399d/mpv-1.0.8-py3-none-any.whl` sha256 `dcf77f612e3f5ce49bd89393f37d286de7ac290db6b0800f1fdcfe0aeb5ba9b8`

- [ ] **Step 1: Write the failing test**

`tests/test_packaging.py`:
```python
import configparser
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FLATPAK = ROOT / "flatpak"
APP_ID = "io.github.striem.Striem"


def manifest():
    return yaml.safe_load((FLATPAK / f"{APP_ID}.yml").read_text())


def all_modules(modules):
    for module in modules:
        if isinstance(module, dict):
            yield module
            yield from all_modules(module.get("modules", []))


def module(name):
    return next(m for m in all_modules(manifest()["modules"]) if m["name"] == name)


def test_manifest_identity_and_runtime():
    m = manifest()
    assert m["id"] == APP_ID
    assert m["command"] == "striem"
    assert (m["runtime"], m["runtime-version"], m["sdk"]) == ("org.kde.Platform", "6.11", "org.kde.Sdk")
    assert (m["base"], m["base-version"]) == ("io.qt.PySide.BaseApp", "6.11")
    assert "/app/cleanup-BaseApp.sh" in m["cleanup-commands"]


def test_manifest_permissions():
    assert set(manifest()["finish-args"]) == {
        "--share=ipc",
        "--share=network",
        "--socket=wayland",
        "--socket=fallback-x11",
        "--device=dri",
        "--socket=pulseaudio",
        "--filesystem=home:ro",
    }


def test_mpv_is_built_as_library_only():
    opts = module("libmpv")["config-opts"]
    assert "-Dlibmpv=true" in opts
    assert "-Dcplayer=false" in opts


def test_files_installed_by_app_module_exist():
    commands = " ".join(module("striem")["build-commands"])
    referenced = [tok for tok in commands.split() if tok.startswith(("flatpak/", "striem"))]
    assert referenced
    for rel in referenced:
        assert (ROOT / rel.rstrip("/")).exists(), rel


def test_desktop_entry():
    entry = configparser.ConfigParser(interpolation=None)
    entry.optionxform = str
    entry.read(FLATPAK / f"{APP_ID}.desktop")
    section = entry["Desktop Entry"]
    assert section["Exec"] == "striem"
    assert section["Icon"] == APP_ID
    assert section["Type"] == "Application"


def test_launcher_runs_package():
    assert "python3 -m striem" in (FLATPAK / "striem.sh").read_text()


def test_build_script_uses_manifest_and_is_executable():
    script = ROOT / "build.sh"
    assert f"flatpak/{APP_ID}.yml" in script.read_text()
    assert os.access(script, os.X_OK)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_packaging.py -v`
Expected: FAIL — `FileNotFoundError` for the manifest.

- [ ] **Step 3: Write the manifest**

`flatpak/io.github.striem.Striem.yml`:
```yaml
id: io.github.striem.Striem
runtime: org.kde.Platform
runtime-version: '6.11'
sdk: org.kde.Sdk
base: io.qt.PySide.BaseApp
base-version: '6.11'
command: striem

finish-args:
  - --share=ipc
  - --share=network
  - --socket=wayland
  - --socket=fallback-x11
  - --device=dri
  - --socket=pulseaudio
  - --filesystem=home:ro

build-options:
  env:
    BASEAPP_REMOVE_WEBENGINE: '1'
    BASEAPP_DISABLE_NUMPY: '1'

cleanup-commands:
  - /app/cleanup-BaseApp.sh

cleanup:
  - /include
  - /lib/pkgconfig
  - /lib/cmake
  - /share/man
  - /share/doc
  - '*.a'
  - '*.la'

modules:
  - name: libplacebo
    buildsystem: meson
    config-opts:
      - -Ddemos=false
    sources:
      - type: git
        url: https://github.com/haasn/libplacebo.git
        tag: v7.360.1
        commit: cee9b076f2c63104ccfd497fa79c39a867293ec4

  - name: libass
    config-opts:
      - --disable-static
    sources:
      - type: archive
        url: https://github.com/libass/libass/releases/download/0.17.5/libass-0.17.5.tar.gz
        sha256: caab4b993dd7be6187c55623b789ed75dddefea6e65938af134637c732fe094a

  - name: libmpv
    buildsystem: meson
    config-opts:
      - -Dlibmpv=true
      - -Dcplayer=false
      - -Dlua=disabled
      - -Djavascript=disabled
      - -Dx11=disabled
      - -Duchardet=disabled
      - -Dlibarchive=disabled
      - -Dalsa=disabled
      - -Dmanpage-build=disabled
      - -Dbuild-date=false
    sources:
      - type: archive
        url: https://github.com/mpv-player/mpv/archive/refs/tags/v0.41.0.tar.gz
        sha256: ee21092a5ee427353392360929dc64645c54479aefdb5babc5cfbb5fad626209

  - name: python-mpv
    buildsystem: simple
    build-commands:
      - pip3 install --no-index --no-deps --no-build-isolation --prefix=${FLATPAK_DEST} mpv-1.0.8-py3-none-any.whl
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/f4/cf/0d5f52753366ecf2c3d763e331dcda54b0f20a1a8e52b175feb9c625399d/mpv-1.0.8-py3-none-any.whl
        sha256: dcf77f612e3f5ce49bd89393f37d286de7ac290db6b0800f1fdcfe0aeb5ba9b8

  - name: striem
    buildsystem: simple
    build-commands:
      - install -d ${FLATPAK_DEST}/share/striem
      - cp -r striem ${FLATPAK_DEST}/share/striem/
      - install -Dm755 flatpak/striem.sh ${FLATPAK_DEST}/bin/striem
      - install -Dm644 flatpak/io.github.striem.Striem.desktop -t ${FLATPAK_DEST}/share/applications
      - install -Dm644 flatpak/io.github.striem.Striem.svg -t ${FLATPAK_DEST}/share/icons/hicolor/scalable/apps
      - install -Dm644 flatpak/io.github.striem.Striem.metainfo.xml -t ${FLATPAK_DEST}/share/metainfo
    sources:
      - type: dir
        path: ..
        skip:
          - .venv
          - .git
          - .flatpak-builder
          - build-dir
          - .pytest_cache
          - shots
```

- [ ] **Step 4: Write launcher, desktop entry, icon, metainfo**

`flatpak/striem.sh`:
```sh
#!/bin/sh
export PYTHONPATH="/app/share/striem${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m striem "$@"
```

`flatpak/io.github.striem.Striem.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Striem
Comment=Watch your home camera streams
Exec=striem
Icon=io.github.striem.Striem
Categories=AudioVideo;Video;Player;
Terminal=false
```

`flatpak/io.github.striem.Striem.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect x="8" y="8" width="112" height="112" rx="24" fill="#1f2a36"/>
  <rect x="20" y="38" width="64" height="52" rx="10" fill="#4fc3a1"/>
  <path d="M84 56 L108 42 V86 L84 72 Z" fill="#4fc3a1"/>
  <circle cx="38" cy="54" r="6" fill="#1f2a36"/>
</svg>
```

`flatpak/io.github.striem.Striem.metainfo.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>io.github.striem.Striem</id>
  <name>Striem</name>
  <summary>Watch your home camera streams</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <description>
    <p>Reads the .xspf playlists in a folder and shows their RTSP camera streams in a grid or one at a time.</p>
  </description>
  <launchable type="desktop-id">io.github.striem.Striem.desktop</launchable>
  <releases>
    <release version="0.1.0" date="2026-09-11"/>
  </releases>
  <content_rating type="oars-1.1"/>
</component>
```

- [ ] **Step 5: Write `build.sh`**

```sh
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
```
Run: `chmod +x build.sh flatpak/striem.sh`

- [ ] **Step 6: Write `README.md`**

````markdown
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
````

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass (packaging 7 new).

- [ ] **Step 8: Commit**

```bash
git add flatpak build.sh README.md tests/test_packaging.py
git commit -m "Add Flatpak packaging and build script"
```

---

### Task 7: End-to-end verification on macOS

**Files:**
- Modify only if a check fails (see Step 5 fallback).

**Interfaces:**
- Consumes: everything above, `scripts/fakecams.sh`, `scripts/snapshot.py`, playlists in `shots/cams` (Task 5 Step 5).
- Produces: screenshots in `shots/` and a pass/fail report.

- [ ] **Step 1: Full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass.

- [ ] **Step 2: Reconnect**

With mediamtx and fakecams running:
```bash
(sleep 6; pkill -f 'lavfi -i mandelbrot'; sleep 9; scripts/fakecams.sh cam3 >/dev/null 2>&1 &) &
.venv/bin/python scripts/snapshot.py --folder shots/cams --out shots wait:9 state shot:dropped wait:14 state shot:recovered
```
Expected: first `state` shows `Camera 3 ... status='Reconnecting in N s'` (or `'Connecting…'`), others `''`; `shots/dropped.png` shows the overlay on tile 3 over its last frame; second `state` shows every status `''`; `shots/recovered.png` shows the fractal moving again.

- [ ] **Step 3: Unreachable camera + broken playlist**

```bash
mkdir -p shots/cams-bad && cp shots/cams/cam1.xspf shots/cams-bad/
printf '<playlist><trackList>' > shots/cams-bad/broken.xspf
cat > shots/cams-bad/dead.xspf <<'EOF'
<?xml version="1.0"?><playlist xmlns="http://xspf.org/ns/0/" version="1"><trackList><track><location>rtsp://127.0.0.1:8554/nothing-here</location><title>Dead</title></track></trackList></playlist>
EOF
.venv/bin/python scripts/snapshot.py --folder shots/cams-bad --out shots wait:4 state shot:bad
```
Expected: `Camera 1` status `''`; `Dead` status starts with `Reconnecting in`; `shots/bad.png` shows a 2×1 grid and the status bar text `Could not read: broken.xspf`.

- [ ] **Step 4: Folder changes keep other streams running**

```bash
mkdir -p shots/cams-live && cp shots/cams/cam1.xspf shots/cams/cam2.xspf shots/cams-live/
(sleep 6; cp shots/cams/cam3.xspf shots/cams-live/; sleep 5; rm shots/cams-live/cam1.xspf) &
.venv/bin/python scripts/snapshot.py --folder shots/cams-live --out shots wait:5 state wait:5 state shot:added wait:5 state shot:removed
```
Expected: states list `Camera 1, Camera 2` → `Camera 1, Camera 2, Camera 3` → `Camera 2, Camera 3`; `Camera 2` never shows `Connecting…` in the later states (it was not restarted).

- [ ] **Step 5: Hidden tiles stay live**

```bash
.venv/bin/python scripts/snapshot.py --folder shots/cams --out shots wait:5 focus:2 wait:30 grid shot:return-a wait:2 shot:return-b
```
Expected: in `shots/return-a.png` and `shots/return-b.png`, the frame counter on Camera 1 (testsrc) differs by about 50 (25 fps × 2 s), i.e. live playback right after returning, not a frozen or slow-motion catch-up.

If Camera 1 is frozen, or the counters differ by clearly more or less than ~50: add a resync on show. In `striem/player.py` add to `MpvWidget`:
```python
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._url and self._render is not None and self._player is not None and self._was_hidden:
            self._player.play(self._url)
        self._was_hidden = False

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._was_hidden = True
```
and initialise `self._was_hidden = False` in `__init__`. Re-run Step 5, then run the full suite and commit with message `Restart hidden streams when shown again`.

- [ ] **Step 6: Clean exit**

Every `snapshot.py` run above must exit with code 0 (no segfault at shutdown). Check with `echo $?` after one run.

- [ ] **Step 7: Report**

List each step's result and attach `shots/grid.png`, `shots/focus.png`, `shots/dropped.png`, `shots/recovered.png`, `shots/bad.png`.
