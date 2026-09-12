"""Remember the chosen playlist folder between launches."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

DEFAULT_FOLDER = Path.home() / "Videos" / "Cameras"
DEFAULT_CAPTURE_FOLDER = Path.home() / "Videos" / "Striem"
DEFAULT_CLIP_SECONDS = 30


class Settings:
    def __init__(self) -> None:
        self._store = QSettings("striem", "Striem")

    def folder(self) -> Path:
        value = self._store.value("folder", "")
        return Path(value) if value else DEFAULT_FOLDER

    def set_folder(self, folder: Path) -> None:
        self._store.setValue("folder", str(folder))

    def capture_folder(self) -> Path:
        value = self._store.value("capture_folder", "")
        return Path(value) if value else DEFAULT_CAPTURE_FOLDER

    def set_capture_folder(self, folder: Path) -> None:
        self._store.setValue("capture_folder", str(folder))

    def clip_seconds(self) -> int:
        # QSettings hands back strings, and a stored 0 is meaningless here.
        value = self._store.value("clip_seconds", 0)
        try:
            return int(value) or DEFAULT_CLIP_SECONDS
        except (TypeError, ValueError):
            return DEFAULT_CLIP_SECONDS

    def set_clip_seconds(self, seconds: int) -> None:
        self._store.setValue("clip_seconds", int(seconds))
