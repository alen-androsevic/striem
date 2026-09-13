"""Name the files written when a camera frame is captured."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from striem.playlist import Camera


def capture_filename(camera_name: str, when: datetime, extension: str = ".png") -> str:
    """File name for something grabbed from `camera_name` at `when`.

    The extension decides what it is: `.png` for a still, `.mkv` for a clip.
    """
    stamp = when.strftime("%Y-%m-%d_%H%M%S")
    safe = camera_name.replace("/", "-").replace("\\", "-").replace(" ", "-")
    return f"{stamp}_{safe}{extension}"


def recording_filename(camera_name: str, when: datetime, part: int = 1) -> str:
    """Name for a forward recording, marked apart from a clip.

    Parts after the first are numbered because mpv overwrites its stream-record
    target: a stream that drops mid-recording has to resume into a new file
    rather than destroying what was already captured.
    """
    marker = "-rec" if part == 1 else f"-rec{part}"
    return capture_filename(camera_name, when, f"{marker}.mkv")


def unique_filename(name: str, taken: Callable[[str], bool]) -> str:
    """`name`, or the first `-2`, `-3`… variant that `taken` does not claim.

    Two captures of one camera within the same second would otherwise collide,
    since the name carries a whole-second timestamp.
    """
    if not taken(name):
        return name
    stem, dot, suffix = name.rpartition(".")
    attempt = 2
    while taken(candidate := f"{stem}-{attempt}{dot}{suffix}"):
        attempt += 1
    return candidate


def capture_path(folder: Path, camera_name: str, when: datetime, extension: str = ".png") -> Path:
    """Where something grabbed from `camera_name` at `when` should be written."""
    name = capture_filename(camera_name, when, extension)
    return folder / unique_filename(name, lambda candidate: (folder / candidate).exists())


def capture_targets(cameras: list[Camera], focused: str | None) -> list[Camera]:
    """Cameras one capture writes: the focused camera alone, or all of them in the grid."""
    if focused is None:
        return list(cameras)
    return [camera for camera in cameras if camera.url == focused]


def available_back_seconds(cache_state: dict) -> float:
    """Seconds of history mpv is actually holding.

    Read from `seekable-ranges`. `demuxer-cache-state` has no `cache-begin`
    field, whatever the first draft of the design claimed; this was verified
    against mpv 0.41.
    """
    ranges = cache_state.get("seekable-ranges") or []
    if not ranges:
        return 0.0
    earliest = min(r["start"] for r in ranges)
    return max(0.0, (cache_state.get("reader-pts") or 0.0) - earliest)


def clip_window(cache_state: dict, seconds: float) -> tuple[float, float] | None:
    """The (start, end) to hand to dump-cache, clamped to what is buffered.

    None when nothing is buffered yet. The end is always bounded on purpose:
    dump-cache with an open end never returns on a live stream, it keeps
    writing as the cache grows.
    """
    ranges = cache_state.get("seekable-ranges") or []
    if not ranges:
        return None
    end = cache_state.get("reader-pts") or 0.0
    earliest = min(r["start"] for r in ranges)
    return max(earliest, end - seconds), end
