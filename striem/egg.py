"""A camera nobody configured: the Konami code adds a live safari feed to the grid."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from striem.playlist import Camera

# WildEarth's 24/7 stream, which is itself a bank of cameras pointed at animals.
# HLS, so mpv plays it through ffmpeg with no yt-dlp in the sandbox.
BONUS_CAMERA = Camera(
    name="🦁 Safari",
    url="https://dqga3jatxofgx.cloudfront.net/WildEarth.m3u8",
    source=Path("<easter egg>"),
)

KONAMI = (
    int(Qt.Key_Up),
    int(Qt.Key_Up),
    int(Qt.Key_Down),
    int(Qt.Key_Down),
    int(Qt.Key_Left),
    int(Qt.Key_Right),
    int(Qt.Key_Left),
    int(Qt.Key_Right),
    int(Qt.Key_B),
    int(Qt.Key_A),
)


class CodeDetector:
    """Watches a key stream for `code`; `feed` is True on the press that completes it."""

    def __init__(self, code: tuple[int, ...] = KONAMI) -> None:
        self._code = tuple(code)
        self._recent: list[int] = []

    def feed(self, key: int) -> bool:
        """Compare the last len(code) keys rather than tracking how far we got: a
        near-miss whose tail is a valid prefix (↑↑↑↓↓…) then keeps working."""
        self._recent.append(int(key))
        if len(self._recent) > len(self._code):
            self._recent.pop(0)
        return tuple(self._recent) == self._code
