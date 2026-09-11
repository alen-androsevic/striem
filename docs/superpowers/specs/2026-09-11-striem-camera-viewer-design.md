# Striem — home camera viewer for Bazzite

Date: 2026-09-11
Status: approved design, pending spec review

## Goal

A local Linux desktop app (target: Bazzite, KDE, immutable) that reads every
`.xspf` playlist in a folder and shows the RTSP camera streams they contain,
either all at once in a grid or one at a time in focus.

Expected scale: 2–6 playlist files, each normally holding one camera. Stream
URLs are plain `rtsp://` without credentials.

## Stack

- Python 3 + PySide6 (Qt 6)
- libmpv via `python-mpv`, rendered with the libmpv OpenGL render API inside a
  `QOpenGLWidget` (Wayland forbids embedding mpv via `--wid`)
- Packaged as a Flatpak

## Components

Each file has one job. `playlist.py`, `layout.py` and `audio.py` import no Qt
and are unit-tested headless.

| File | Responsibility | Depends on |
|---|---|---|
| `striem/playlist.py` | `load_cameras(folder) -> (cameras, errors)`. Parses every `*.xspf` in the folder (non-recursive, sorted by filename). Each `<track>` becomes a `Camera(name, url, source)`. Name = track `<title>`, else the file stem (with ` 2`, ` 3`… suffix when one file holds several untitled tracks). VLC `<extension>` elements are ignored. Tracks without `<location>` are skipped. Unparseable files are reported in `errors` as `(path, message)`, never raised. Duplicate URLs across files are kept once (first wins). | stdlib (`xml.etree`, `urllib.parse`) |
| `striem/layout.py` | `grid_dims(n) -> (cols, rows)`: 0→(0,0), 1→1×1, 2→2×1, 3–4→2×2, 5–6→3×2, 7–9→3×3, beyond: `cols = ceil(sqrt(n))`, `rows = ceil(n / cols)`. Also `diff_cameras(old, new) -> (added, removed, kept)` keyed by URL. | stdlib |
| `striem/audio.py` | `AudioState`: at most one camera unmuted. Operations: `toggle(cam)`, `focus(cam)`, `toggle_mute()`; query `is_unmuted(cam)`. Rules below. | nothing |
| `striem/player.py` | `MpvWidget(QOpenGLWidget)`: one mpv instance with its render context; `play(url)`, `set_muted(bool)`, `stop()`; emits Qt signals for `playing`, `ended/error`. | PySide6, python-mpv |
| `striem/tile.py` | `CameraTile`: `MpvWidget` + name label + status overlay + 🔈/🔇 button. Owns the reconnect timer. Emits `clicked` and `audioClicked`. | `player.py` |
| `striem/window.py` | `MainWindow`: toolbar, grid, focus mode, keyboard shortcuts, folder watching, empty state. Wires `AudioState` to tiles. | all above |
| `striem/settings.py` | Persist chosen folder via `QSettings`; default `~/Videos/Cameras`. | PySide6 |
| `striem/__main__.py` | Entry point (`python -m striem`, installed as `striem`). | `window.py` |

## Behaviour

### Grid and focus
- Startup shows all cameras in a grid sized by `grid_dims`, tile order = camera
  order from `load_cameras`. Each tile shows its name in a corner.
- Click a tile, or press `1`–`9`, to focus that camera: it fills the window.
  `Esc`, `0`, or clicking the focused tile returns to the grid.
- Focus is implemented by hiding the other tiles and letting the focused tile
  span the grid (no reparenting — reparenting a `QOpenGLWidget` recreates its GL
  context). Hidden tiles keep decoding so returning to the grid is instant.
- `F11` toggles window fullscreen.

### Toolbar
`All` button, one button per camera (focuses it), `Choose folder…`, mute
toggle. A status bar message lists playlist files that failed to parse.

### Audio (at most one camera unmuted)
State: `active` (camera or none) and `muted` (bool, the `M` toggle).
A camera is audible iff it is `active` and not `muted`.
- Tile 🔈 button on a camera that is not audible → it becomes `active`,
  `muted = False`; the previous camera goes silent.
- Tile 🔈 button on the audible camera → `active = none`.
- Focusing a camera → it becomes `active`, `muted = False`. Returning to the
  grid does not change audio.
- `M` / toolbar mute → flips `muted`; `active` is remembered, so pressing again
  restores sound on the same camera. With no `active` camera, `M` does nothing.
- When the active camera is removed (folder change), `active = none`.

### Stream settings (per mpv instance)
`profile=low-latency`, `rtsp-transport=tcp`, `cache=no`,
`hwdec=auto-copy-safe`, `vo=libmpv`, `mute=yes` initially, `keep-open=yes`,
audio via PulseAudio.

- `keep-open=yes` makes mpv hold the last frame when a live stream drops.
- Copy-back hwdec is used because direct VA-API interop through the libmpv
  render API on Wayland needs a `wl_display` handle that PySide6 does not
  readily expose.
- python-mpv finds libmpv only through `ctypes.util.find_library('mpv')`, so
  `player.py` answers that lookup with `/app/lib/libmpv.so.2` (Flatpak) or
  `/opt/homebrew/lib/libmpv.dylib` (macOS dev) when present.

### Reconnect
Signals, verified against mpv 0.41 with a local mediamtx:
- a live stream that drops sets `eof-reached=True` (no `end-file` event)
- a stream that cannot be reached emits `end-file` with `reason=error`
- a successful (re)start emits `playback-restart`
- a stream that opens but never delivers frames emits nothing at all
  (measured: `file-loaded`, then silence for 75 s; `network-timeout` does not
  cover it), so the player runs a connect watchdog: if `playback-restart` has
  not arrived within 10 s of a (re)connect attempt, that attempt counts as
  failed. Streams that stall mid-playback without EOF are not detected
  (known limitation).

On either failure signal the tile keeps its last frame, overlays
"Reconnecting in N s", and retries. Backoff: 2, 4, 8, 16, 30, 30… seconds;
reset to 2 s once playback starts. Initial state shows "Connecting…". Each tile
reconnects independently.

### Folder watching
`QFileSystemWatcher` on the folder (and its files). Changes are debounced by
500 ms, then `load_cameras` runs and `diff_cameras` decides which tiles to
create or destroy; kept tiles (same URL) keep playing. A renamed title updates
the label without restarting the stream. If the folder is missing or empty, the
window shows "No .xspf playlists in <folder>" with a `Choose folder…` button.
Choosing a folder saves it via `settings.py` and rescans.

## Packaging (Flatpak)

- App id `io.github.striem.Striem`; runtime `org.kde.Platform` (current Qt 6
  branch), SDK `org.kde.Sdk`, base app `io.qt.PySide.BaseApp` of the matching
  branch.
- libmpv built in the manifest with its dependencies (following Haruna's
  Flathub manifest as reference); `python-mpv` installed via pip module.
- H.264/H.265 via the runtime's ffmpeg / codecs extension.
- `finish-args`: `--share=ipc` (X11 fallback), `--share=network`, `--socket=wayland`,
  `--socket=fallback-x11`, `--device=dri`, `--socket=pulseaudio`,
  `--filesystem=home:ro`.
- Ships a `.desktop` file, an SVG icon and a metainfo file.
- `build.sh`: installs `org.flatpak.Builder` from Flathub if missing, adds the
  Flathub remote for the user if missing, then builds and installs the app with
  `--user --install --install-deps-from=flathub`. No sudo.

## Testing

- **Unit (pytest, headless, on macOS):** `playlist.py` against fixtures — a
  VLC-generated playlist with `vlc:` extensions, multiple tracks in one file,
  missing title, missing location, malformed XML, URL-encoded characters,
  duplicate URLs across files, non-`.xspf` files ignored. `layout.py` grid
  sizes and diffing. `audio.py` every rule above.
- **Integration (manual, on macOS):** mediamtx serving four ffmpeg test-pattern
  RTSP streams; run the app from source with Homebrew `mpv` + pip `PySide6`.
  Verify grid, focus, the one-unmuted rule, and reconnect after killing and
  restarting one stream; capture screenshots.
- **Flatpak build:** run `./build.sh` on Bazzite (cannot run on macOS). This is
  the one step the user runs.

## Out of scope

PTZ control, recording, snapshots, motion detection, authentication handling,
recursive folder scan, editing playlists from the app.
