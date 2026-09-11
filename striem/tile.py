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
