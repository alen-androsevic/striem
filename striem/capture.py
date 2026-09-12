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
