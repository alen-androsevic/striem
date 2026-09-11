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
