# Clips and Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `C` key that saves the last N seconds of each on-screen camera retroactively, and an `R` key that records forward until stopped.

**Architecture:** Enable mpv's demuxer back buffer (`cache=yes`, `demuxer_max_back_bytes`) plus the one option that makes container writing work (`demuxer_lavf_probe_info=yes`). Clips use a bounded `dump-cache`; recordings use the `stream_record` property. All naming and target selection stays in the Qt-free `striem/capture.py`, which is unit-tested; Qt wiring is verified with `scripts/snapshot.py` against `scripts/fakecams.sh`.

**Tech Stack:** Python 3.11+, PySide6 (Qt 6), libmpv via python-mpv 1.0.8, Flatpak, pytest.

**Spec:** `docs/superpowers/specs/2026-09-12-striem-clip-recording-design.md`

## Global Constraints

- `striem/capture.py` imports no Qt. It may import `striem.playlist` only.
- Tests never instantiate Qt widgets. Pure functions and constants only.
- Run tests with `.venv/bin/python -m pytest -q` from the repo root.
- `dump-cache` MUST always be given a bounded `end`. `end="no"` on a live stream never returns.
- `demuxer-cache-state` has no `cache-begin` field. Use `seekable-ranges`.
- Status messages use `self.statusBar().showMessage(text, 5000)`.
- Commit messages: imperative mood, sentence case, no attribution trailers.
- Target 30 s default clip length; 32 MiB back buffer per camera.

---

### Task 1: Move the capture folder to ~/Videos/Striem

**Files:**
- Modify: `striem/settings.py`
- Modify: `flatpak/io.github.striem.Striem.yml:16-17`
- Test: `tests/test_settings.py`, `tests/test_packaging.py:40-50`

**Interfaces:**
- Consumes: nothing
- Produces: `DEFAULT_CAPTURE_FOLDER = Path.home() / "Videos" / "Striem"`

- [ ] **Step 1: Update the failing tests first**

In `tests/test_settings.py` replace the capture-folder assertion:

```python
def test_default_capture_folder_matches_spec():
    assert DEFAULT_CAPTURE_FOLDER == Path.home() / "Videos" / "Striem"
```

In `tests/test_packaging.py::test_manifest_permissions` swap the grant:

```python
        "--filesystem=home:ro",
        "--filesystem=xdg-videos/Striem:create",
    }
```

- [ ] **Step 2: Run to verify both fail**

Run: `.venv/bin/python -m pytest tests/test_settings.py tests/test_packaging.py -q`
Expected: FAIL — settings still says Pictures, manifest still says `xdg-pictures:create`.

- [ ] **Step 3: Make them pass**

In `striem/settings.py`:

```python
DEFAULT_CAPTURE_FOLDER = Path.home() / "Videos" / "Striem"
```

In `flatpak/io.github.striem.Striem.yml`, replace the `xdg-pictures` line:

```yaml
  - --filesystem=home:ro
  - --filesystem=xdg-videos/Striem:create
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 5: Update the README row**

Change `~/Pictures/Striem` to `~/Videos/Striem` in the "Save a frame" row of the Use table.

- [ ] **Step 6: Commit**

```bash
git add striem/settings.py flatpak/io.github.striem.Striem.yml tests/test_settings.py tests/test_packaging.py README.md
git commit -m "Move captures to ~/Videos/Striem with a narrower grant"
```

---

### Task 2: Enable the back buffer

**Files:**
- Modify: `striem/player.py:32-40`
- Test: `tests/test_tile.py:12-21`

**Interfaces:**
- Consumes: nothing
- Produces: `MPV_OPTIONS` containing `cache="yes"`, `demuxer_lavf_probe_info="yes"`, `demuxer_max_back_bytes="32MiB"`

- [ ] **Step 1: Update the pinned contract test**

In `tests/test_tile.py`:

```python
def test_mpv_options_match_spec():
    assert MPV_OPTIONS == {
        "vo": "libmpv",
        "profile": "low-latency",
        "rtsp_transport": "tcp",
        "cache": "yes",
        "hwdec": "auto-copy-safe",
        "keep_open": "yes",
        "mute": "yes",
        "demuxer_lavf_probe_info": "yes",
        "demuxer_max_back_bytes": "32MiB",
    }
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_tile.py -q`
Expected: FAIL — `cache` is still `"no"` and the two keys are absent.

- [ ] **Step 3: Change MPV_OPTIONS**

In `striem/player.py`:

```python
MPV_OPTIONS = {
    "vo": "libmpv",
    "profile": "low-latency",
    "rtsp_transport": "tcp",
    "cache": "yes",
    "hwdec": "auto-copy-safe",
    "keep_open": "yes",
    "mute": "yes",
    # The low-latency profile sets demuxer-lavf-probe-info=nostreams, which makes
    # mpv write 0-byte containers. This override is the one thing that makes
    # dump-cache and stream-record produce valid files; it costs no measurable
    # startup latency (measured 1.56s vs 1.57s).
    "demuxer_lavf_probe_info": "yes",
    "demuxer_max_back_bytes": "32MiB",
}
```

- [ ] **Step 4: Run tests, then verify streams still play**

Run: `.venv/bin/python -m pytest -q` — expected PASS.

Then, with `mediamtx` and `scripts/fakecams.sh` running, confirm live playback is unaffected:

```bash
.venv/bin/python scripts/snapshot.py --folder <cams> --out /tmp/out wait:8 state
```
Expected: every camera reports `status=''` (playing, no reconnect message).

- [ ] **Step 5: Commit**

```bash
git add striem/player.py tests/test_tile.py
git commit -m "Keep a back buffer so the last seconds can be saved"
```

---

### Task 3: Give the name helpers an extension

**Files:**
- Modify: `striem/capture.py`
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: `capture_filename(camera_name, when)`, `capture_path(folder, camera_name, when)`
- Produces: `capture_filename(camera_name, when, extension=".png")`, `capture_path(folder, camera_name, when, extension=".png")`

- [ ] **Step 1: Write the failing test**

```python
def test_filename_takes_an_extension():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert capture_filename("Front Door", when, ".mkv") == "2026-09-12_143005_Front-Door.mkv"


def test_capture_path_carries_the_extension(tmp_path):
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert capture_path(tmp_path, "Cam", when, ".mkv") == tmp_path / "2026-09-12_143005_Cam.mkv"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_capture.py -q`
Expected: FAIL — `capture_filename() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Add the parameter**

```python
def capture_filename(camera_name: str, when: datetime, extension: str = ".png") -> str:
    """File name for a frame grabbed from `camera_name` at `when`."""
    stamp = when.strftime("%Y-%m-%d_%H%M%S")
    safe = camera_name.replace("/", "-").replace("\\", "-").replace(" ", "-")
    return f"{stamp}_{safe}{extension}"


def capture_path(folder: Path, camera_name: str, when: datetime, extension: str = ".png") -> Path:
    """Where a frame grabbed from `camera_name` at `when` should be written."""
    name = capture_filename(camera_name, when, extension)
    return folder / unique_filename(name, lambda candidate: (folder / candidate).exists())
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. The existing `.png` tests still pass because the default is unchanged — that is the point of the default.

- [ ] **Step 5: Commit**

```bash
git add striem/capture.py tests/test_capture.py
git commit -m "Let the capture names carry an extension"
```

---

### Task 4: Name recordings and their parts

**Files:**
- Modify: `striem/capture.py`
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: `capture_filename`
- Produces: `recording_filename(camera_name, when, part=1) -> str`

- [ ] **Step 1: Write the failing tests**

```python
def test_recording_filename_marks_a_recording():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert recording_filename("Front Door", when) == "2026-09-12_143005_Front-Door-rec.mkv"


def test_recording_filename_numbers_later_parts():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert recording_filename("Cam", when, part=2) == "2026-09-12_143005_Cam-rec2.mkv"
    assert recording_filename("Cam", when, part=3) == "2026-09-12_143005_Cam-rec3.mkv"
```

Add `recording_filename` to the import at the top of the file.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_capture.py -q`
Expected: FAIL — `cannot import name 'recording_filename'`.

- [ ] **Step 3: Implement it**

```python
def recording_filename(camera_name: str, when: datetime, part: int = 1) -> str:
    """Name for a forward recording. Parts after the first are numbered, because a
    stream that drops mid-recording resumes into a new file rather than
    overwriting what was already captured."""
    marker = "-rec" if part == 1 else f"-rec{part}"
    return capture_filename(camera_name, when, f"{marker}.mkv")
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add striem/capture.py tests/test_capture.py
git commit -m "Name recordings apart from clips"
```

---

### Task 5: Work out how much history is buffered

**Files:**
- Modify: `striem/capture.py`
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: nothing
- Produces: `available_back_seconds(cache_state) -> float`, `clip_window(cache_state, seconds) -> tuple[float, float] | None`

**Context:** `demuxer-cache-state` has **no** `cache-begin`. Verified keys include `reader-pts` and `seekable-ranges`, a list of `{"start": float, "end": float}`. This is why the function takes a plain dict — it is pure and testable without mpv.

- [ ] **Step 1: Write the failing tests**

```python
def test_available_back_seconds_uses_the_oldest_seekable_range():
    state = {"reader-pts": 20.7, "seekable-ranges": [{"start": 0.7, "end": 20.2}]}
    assert available_back_seconds(state) == pytest.approx(20.0)


def test_available_back_seconds_is_zero_without_ranges():
    assert available_back_seconds({"reader-pts": 5.0, "seekable-ranges": []}) == 0.0


def test_clip_window_is_the_requested_span_when_buffered():
    state = {"reader-pts": 100.0, "seekable-ranges": [{"start": 10.0, "end": 99.0}]}
    assert clip_window(state, 30) == (70.0, 100.0)


def test_clip_window_clamps_to_what_is_buffered():
    state = {"reader-pts": 20.0, "seekable-ranges": [{"start": 12.0, "end": 19.5}]}
    assert clip_window(state, 30) == (12.0, 20.0)


def test_clip_window_is_none_when_nothing_is_buffered():
    assert clip_window({"reader-pts": 3.0, "seekable-ranges": []}, 30) is None
```

Add `import pytest` at the top of `tests/test_capture.py`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_capture.py -q`
Expected: FAIL — `cannot import name 'available_back_seconds'`.

- [ ] **Step 3: Implement both**

```python
def available_back_seconds(cache_state: dict) -> float:
    """Seconds of history mpv is actually holding.

    Derived from `seekable-ranges`, because `demuxer-cache-state` has no
    `cache-begin` field despite what the first draft of the spec assumed.
    """
    ranges = cache_state.get("seekable-ranges") or []
    if not ranges:
        return 0.0
    earliest = min(r["start"] for r in ranges)
    return max(0.0, (cache_state.get("reader-pts") or 0.0) - earliest)


def clip_window(cache_state: dict, seconds: float) -> tuple[float, float] | None:
    """The (start, end) to hand to dump-cache, clamped to what is buffered.

    None when nothing is buffered yet. The end is always bounded: dump-cache
    with an open end never returns on a live stream.
    """
    ranges = cache_state.get("seekable-ranges") or []
    if not ranges:
        return None
    end = cache_state.get("reader-pts") or 0.0
    earliest = min(r["start"] for r in ranges)
    return max(earliest, end - seconds), end
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add striem/capture.py tests/test_capture.py
git commit -m "Work out how much history the buffer actually holds"
```

---

### Task 6: Dump a clip from one player

**Files:**
- Modify: `striem/player.py`
- Modify: `striem/tile.py`

**Interfaces:**
- Consumes: `clip_window(cache_state, seconds)`
- Produces: `MpvWidget.clip_to(path, seconds) -> float` (seconds written, 0.0 on failure); `CameraTile.clip_to(path, seconds) -> float`

- [ ] **Step 1: Add clip_to to MpvWidget**

In `striem/player.py`, after `capture_to`:

```python
    def clip_to(self, path, seconds: float) -> float:
        """Write the buffered last `seconds` to `path`. Returns the duration actually
        written, or 0.0 if nothing could be saved.

        The end is always bounded: dump-cache with end="no" never returns on a
        live stream, it keeps writing as the cache grows.
        """
        if self._player is None:
            return 0.0
        try:
            window = clip_window(self._player.demuxer_cache_state or {}, seconds)
            if window is None:
                return 0.0
            begin, end = window
            self._player.command("dump-cache", begin, end, str(path))
        except Exception:  # a failed dump must never take the window down
            return 0.0
        return end - begin
```

Add the import at the top of `striem/player.py`:

```python
from striem.capture import clip_window
```

- [ ] **Step 2: Add clip_to to CameraTile**

In `striem/tile.py`, beside `capture_to`:

```python
    def clip_to(self, path, seconds: float) -> float:
        """Write the buffered last `seconds`. 0.0 while the stream is not playing."""
        if not self._playing:
            return 0.0
        return self.video.clip_to(path, seconds)
```

- [ ] **Step 3: Run the suite for regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. No new unit tests here — this is Qt and mpv wiring, verified in Task 7.

- [ ] **Step 4: Commit**

```bash
git add striem/player.py striem/tile.py
git commit -m "Dump the buffered window to a file"
```

---

### Task 7: The clip key

**Files:**
- Modify: `striem/window.py`
- Modify: `scripts/snapshot.py`

**Interfaces:**
- Consumes: `CameraTile.clip_to`, `capture_targets`, `capture_path`, `Settings.clip_seconds`
- Produces: `MainWindow.clip() -> list[Path]`

- [ ] **Step 1: Add the clip_seconds setting**

In `striem/settings.py`:

```python
DEFAULT_CLIP_SECONDS = 30


    def clip_seconds(self) -> int:
        value = self._store.value("clip_seconds", 0)
        try:
            return int(value) or DEFAULT_CLIP_SECONDS
        except (TypeError, ValueError):
            return DEFAULT_CLIP_SECONDS

    def set_clip_seconds(self, seconds: int) -> None:
        self._store.setValue("clip_seconds", int(seconds))
```

Add to `tests/test_settings.py`:

```python
def test_default_clip_seconds_matches_spec():
    assert DEFAULT_CLIP_SECONDS == 30
```

- [ ] **Step 2: Add clip() to MainWindow**

In `striem/window.py`, after `capture()`:

```python
    def clip(self) -> list[Path]:
        """Save the buffered last seconds of the focused camera, or of every camera."""
        targets = capture_targets(self._cameras, self._focused)
        if not targets:
            self.statusBar().showMessage("No cameras to clip", 5000)
            return []
        folder = self._settings.capture_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not save to {_pretty(folder)}: {exc}", 5000)
            return []
        seconds = self._settings.clip_seconds()
        when = datetime.now()
        saved: list[Path] = []
        longest = 0.0
        for camera in targets:
            tile = self._tiles.get(camera.url)
            if tile is None:
                continue
            path = capture_path(folder, camera.name, when, ".mkv")
            written = tile.clip_to(path, seconds)
            if written > 0:
                saved.append(path)
                longest = max(longest, written)
        self._report_clip(saved, longest, folder)
        return saved

    def _report_clip(self, saved: list[Path], seconds: float, folder: Path) -> None:
        if not saved:
            self.statusBar().showMessage("Nothing buffered to clip yet", 5000)
            return
        what = saved[0].name if len(saved) == 1 else f"{len(saved)} clips"
        self.statusBar().showMessage(
            f"Saved {what} ({seconds:.0f}s) to {_pretty(folder)}", 5000
        )
```

- [ ] **Step 3: Bind the key and toolbar action**

In `_build_shortcuts`:

```python
        QShortcut(QKeySequence("C"), self, activated=self.clip)
```

In `_build_toolbar`, beside the capture action:

```python
        self._clip_action = QAction("Clip", self)
        self._clip_action.setToolTip("Save the buffered last seconds (C)")
        self._clip_action.triggered.connect(self.clip)
```

and add `self._toolbar.addAction(self._clip_action)` directly after the capture action.

- [ ] **Step 4: Add a harness step**

In `scripts/snapshot.py`, beside the `capture` step:

```python
        elif command == "clip":
            for path in window.clip():
                print("clipped", path, flush=True)
```

and add `clip` to the Steps line in the docstring.

- [ ] **Step 5: Verify end to end**

With `mediamtx` and `scripts/fakecams.sh` running:

```bash
.venv/bin/python scripts/snapshot.py --folder <cams> --out /tmp/out wait:20 clip focus:1 wait:3 clip state
```

Expected: the first `clip` prints one path per camera, the second prints exactly one. Then check each file is a real clip:

```bash
for f in /tmp/out/*.mkv; do ffprobe -v error -show_entries format=duration -show_entries stream=codec_name -of csv=p=0 "$f"; done
```
Expected: `h264`, `aac`, and a duration in the region of 20 s for the first burst.

- [ ] **Step 6: Commit**

```bash
git add striem/window.py striem/settings.py tests/test_settings.py scripts/snapshot.py
git commit -m "Add a clip key that saves the buffered last seconds"
```

---

### Task 8: Start and stop recording on one player

**Files:**
- Modify: `striem/player.py`
- Modify: `striem/tile.py`

**Interfaces:**
- Consumes: nothing
- Produces: `MpvWidget.start_recording(path) -> bool`, `MpvWidget.stop_recording() -> None`, `CameraTile.start_recording(path) -> bool`, `CameraTile.stop_recording() -> None`, `CameraTile.recording` (bool attribute)

- [ ] **Step 1: Add the two methods to MpvWidget**

```python
    def start_recording(self, path) -> bool:
        """Begin writing incoming data to `path`. mpv overwrites the file, so never
        reuse a path for a second part of the same recording."""
        if self._player is None:
            return False
        try:
            self._player.stream_record = str(path)
        except Exception:
            return False
        return True

    def stop_recording(self) -> None:
        """Stop writing and let mpv finalise the container. Safe to call when idle."""
        if self._player is None:
            return
        try:
            self._player.stream_record = ""
        except Exception:
            pass
```

- [ ] **Step 2: Add them to CameraTile**

```python
    def start_recording(self, path, when=None, part: int = 1) -> bool:
        """Begin recording to `path`. `when` and `part` are remembered so that a
        reconnect can resume into a NEW part instead of overwriting this file:
        mpv always overwrites the stream-record target."""
        if not self._playing:
            return False
        if not self.video.start_recording(path):
            return False
        self.recording = True
        self._recording_when = when or datetime.now()
        self._recording_part = part
        self._recording_folder = Path(path).parent
        self._rec.show()
        self._rec.raise_()
        self._place_overlays()
        return True

    def stop_recording(self) -> None:
        self.video.stop_recording()
        self.recording = False
        self._recording_folder = None
        self._rec.hide()
```

In `CameraTile.__init__`, beside `self.audible = False`:

```python
        self.recording = False
        self._recording_when = None
        self._recording_part = 1
        self._recording_folder = None
```

Add these imports to the top of `striem/tile.py`:

```python
from datetime import datetime
from pathlib import Path
```

and create the indicator beside the other overlays:

```python
        self._rec = QLabel("● REC", self)
        self._rec.setStyleSheet(
            "color: #ff4444; background: rgba(0, 0, 0, 150); padding: 3px 8px; border-radius: 4px;"
        )
        self._rec.hide()
```

- [ ] **Step 3: Place the indicator bottom-left**

In `_place_overlays`, after the existing placements:

```python
        self._rec.adjustSize()
        self._rec.raise_()
        self._rec.move(_MARGIN, self.height() - self._rec.height() - _MARGIN)
```

Do **not** add `self._rec` to the existing `for label in (...)` loop above it. That loop
anchors its labels to the top of the tile, and the REC indicator is anchored to the
bottom; folding it in would place it under the camera name.

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add striem/player.py striem/tile.py
git commit -m "Let a tile record its stream to a file"
```

---

### Task 9: The record key and its locked set

**Files:**
- Modify: `striem/window.py`
- Modify: `scripts/snapshot.py`

**Interfaces:**
- Consumes: `CameraTile.start_recording`, `CameraTile.stop_recording`, `recording_filename`, `capture_targets`
- Produces: `MainWindow.toggle_recording() -> bool` (True when recording started)

- [ ] **Step 1: Add the state and the toggle**

In `MainWindow.__init__`, beside `self._focused`:

```python
        self._recording: list[Camera] = []
```

Then:

```python
    def toggle_recording(self) -> bool:
        """Start recording the cameras on screen, or stop whatever is recording."""
        if self._recording:
            self._stop_recording()
            return False
        return self._start_recording()

    def _start_recording(self) -> bool:
        targets = capture_targets(self._cameras, self._focused)
        if not targets:
            self.statusBar().showMessage("No cameras to record", 5000)
            return False
        folder = self._settings.capture_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not save to {_pretty(folder)}: {exc}", 5000)
            return False
        when = datetime.now()
        started: list[Camera] = []
        for camera in targets:
            tile = self._tiles.get(camera.url)
            if tile is None:
                continue
            name = recording_filename(camera.name, when)
            path = folder / unique_filename(name, lambda c: (folder / c).exists())
            if tile.start_recording(path):
                started.append(camera)
        if not started:
            # Never show recording that is not happening.
            self.statusBar().showMessage("Could not start recording", 5000)
            return False
        # The set is locked here: changing view never changes what is recording.
        self._recording = started
        self._record_action.setChecked(True)
        self.statusBar().showMessage(
            f"Recording {len(started)} camera{'s' if len(started) > 1 else ''} "
            f"to {_pretty(folder)}", 5000)
        return True

    def _stop_recording(self) -> None:
        stopped = 0
        for camera in self._recording:
            tile = self._tiles.get(camera.url)
            if tile is not None:
                tile.stop_recording()
                stopped += 1
        self._recording = []
        self._record_action.setChecked(False)
        self.statusBar().showMessage(f"Stopped recording {stopped} cameras", 5000)
```

Add to the imports in `striem/window.py`:

```python
from striem.capture import capture_path, capture_targets, recording_filename, unique_filename
```

- [ ] **Step 2: Bind the key and the checkable action**

In `_build_shortcuts`:

```python
        QShortcut(QKeySequence("R"), self, activated=self.toggle_recording)
```

In `_build_toolbar`:

```python
        self._record_action = QAction("Record", self)
        self._record_action.setCheckable(True)
        self._record_action.setToolTip("Record the cameras on screen until stopped (R)")
        self._record_action.triggered.connect(self.toggle_recording)
```

and add it to the toolbar directly after the clip action.

- [ ] **Step 3: Drop removed cameras from the locked set**

In `rescan()`, inside the `for camera in removed:` loop, beside `self._audio.forget(camera.url)`:

```python
            self._recording = [c for c in self._recording if c.url != camera.url]
```

- [ ] **Step 4: Stop recordings before shutdown**

Replace `closeEvent`:

```python
    def closeEvent(self, event) -> None:
        # Stop first so mpv finalises each container; shutting the player down
        # mid-recording leaves an unplayable file.
        if self._recording:
            self._stop_recording()
        for tile in self._tiles.values():
            tile.shutdown()
        super().closeEvent(event)
```

- [ ] **Step 5: Add harness steps**

In `scripts/snapshot.py`:

```python
        elif command == "record":
            print("recording:", window.toggle_recording(), flush=True)
```

and add `record` to the docstring Steps line.

- [ ] **Step 6: Verify end to end**

```bash
.venv/bin/python scripts/snapshot.py --folder <cams> --out /tmp/rec wait:8 record wait:6 record wait:1 state
```
Expected: `recording: True` then `recording: False`, and one `*-rec.mkv` per camera. Check each plays:

```bash
for f in /tmp/rec/*-rec.mkv; do ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"; done
```
Expected: a duration near 6 s, not an EBML error.

- [ ] **Step 7: Commit**

```bash
git add striem/window.py scripts/snapshot.py
git commit -m "Record the cameras on screen until stopped"
```

---

### Task 10: Survive a stream dropping mid-recording

**Files:**
- Modify: `striem/tile.py`

**Interfaces:**
- Consumes: `recording_filename(camera_name, when, part)`
- Produces: `CameraTile` resuming into `-rec2`, `-rec3`, … after a reconnect

**Context:** mpv **overwrites** the `stream-record` file. Re-arming with the same path after a reconnect would destroy what was already captured, so each resumption gets a new part.

- [ ] **Step 1: Add the signal**

`start_recording` already records `_recording_when`, `_recording_part` and
`_recording_folder` (Task 8), so nothing about it changes here. Add one signal
beside the existing `clicked` and `audioClicked` declarations in `CameraTile`:

```python
    recordingResumed = Signal(object, str)  # (Camera, new file name)
```

and the naming import at the top of `striem/tile.py`:

```python
from striem.capture import recording_filename
```

- [ ] **Step 2: Resume into a new part when playback returns**

In `_on_playing`, after `self._playing = True`:

```python
        if self.recording and self._recording_folder is not None:
            # mpv overwrites the stream-record target, so resume into a new part
            # rather than destroying what was captured before the drop.
            self._recording_part += 1
            name = recording_filename(self.camera.name, self._recording_when, self._recording_part)
            if self.video.start_recording(self._recording_folder / name):
                self.recordingResumed.emit(self.camera, name)
```

- [ ] **Step 3: Report it in the window**

In `MainWindow`, connect the signal where the other tile signals are connected in `rescan()`:

```python
            tile.recordingResumed.connect(self._on_recording_resumed)
```

and add:

```python
    def _on_recording_resumed(self, camera, name: str) -> None:
        self.statusBar().showMessage(f"{camera.name} reconnected — recording continues in {name}", 5000)
```

- [ ] **Step 4: Verify by killing a stream**

Start recording, then kill one publisher and let it come back:

```bash
pkill -f "rtsp://127.0.0.1:8554/cam1"
scripts/fakecams.sh cam1 &
```
Expected: a `-rec2.mkv` appears beside the original `-rec.mkv`, and the original is still playable.

- [ ] **Step 5: Commit**

```bash
git add striem/tile.py striem/window.py
git commit -m "Resume recording into a new part after a reconnect"
```

---

### Task 11: Tidy the toolbar

**Files:**
- Modify: `striem/window.py:154-178`

**Interfaces:**
- Consumes: the existing actions
- Produces: the toolbar laid out as `All | cameras | … | Capture Clip Record | Mute | ⋮`

- [ ] **Step 1: Group the capture actions and move the folders into a menu**

Replace the toolbar assembly at the end of `_build_toolbar`:

```python
        menu = QMenu(self)
        menu.addAction(self._folder_action)
        menu.addAction(self._capture_folder_action)
        menu.addAction(self._clip_length_action)
        overflow = QToolButton(self)
        overflow.setText("⋮")
        overflow.setMenu(menu)
        overflow.setPopupMode(QToolButton.InstantPopup)

        self._toolbar.addAction(self._all_action)
        self._camera_anchor = self._toolbar.addSeparator()
        self._toolbar.addWidget(spacer)
        self._toolbar.addAction(self._capture_action)
        self._toolbar.addAction(self._clip_action)
        self._toolbar.addAction(self._record_action)
        self._toolbar.addSeparator()
        self._toolbar.addAction(self._mute_action)
        self._toolbar.addWidget(overflow)
```

Add `QMenu` and `QToolButton` to the `PySide6.QtWidgets` import list.

- [ ] **Step 2: Add the clip length prompt**

```python
        self._clip_length_action = QAction("Clip length…", self)
        self._clip_length_action.triggered.connect(self._choose_clip_length)
```

and:

```python
    def _choose_clip_length(self) -> None:
        seconds, ok = QInputDialog.getInt(
            self, "Clip length", "Seconds to save when clipping:",
            self._settings.clip_seconds(), 1, 300)
        if ok:
            self._settings.set_clip_seconds(seconds)
```

Add `QInputDialog` to the imports.

- [ ] **Step 3: Run the suite and eyeball the window**

Run: `.venv/bin/python -m pytest -q` — expected PASS.

Then launch the app and confirm the toolbar reads `All | cameras | … | Capture Clip Record | Mute | ⋮`, and that the menu holds all three entries.

- [ ] **Step 4: Commit**

```bash
git add striem/window.py
git commit -m "Group the capture actions and move settings into a menu"
```

---

### Task 12: Document it

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the two rows to the Use table**

```markdown
| Save a clip | `C` or **Clip**. The last 30 seconds of the focused camera, or of every camera from the grid. Change the length with **Clip length…** |
| Record | `R` or **Record**. Starts the cameras on screen recording until pressed again; what was on screen when you started keeps recording however you navigate |
```

- [ ] **Step 2: Note the buffer in the Use section**

Add below the table:

```markdown
Striem keeps the last seconds of every camera in memory so a clip can be saved
after the fact, about 32 MiB per camera. Clips and recordings are written as
`.mkv` alongside the stills in `~/Videos/Striem`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document the clip and record keys"
```

---

## Verification before calling it done

- [ ] `.venv/bin/python -m pytest -q` passes with no warnings
- [ ] A grid clip writes one playable `.mkv` per camera; a focused clip writes exactly one
- [ ] A recording started in the grid keeps all cameras recording after focusing one
- [ ] Pressing `C` during a recording writes a clip and leaves the recording running and playable
- [ ] Quitting mid-recording leaves playable files
- [ ] Killing a stream mid-recording produces a `-rec2` part and leaves the first part playable
- [ ] **Flatpak build on Bazzite** — the grant `xdg-videos/Striem:create` cannot be verified on macOS
