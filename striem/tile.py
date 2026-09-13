"""One camera in the grid: video, name label, status overlay and speaker button."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from striem.capture import recording_filename
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
    recordingResumed = Signal(object, str)  # (Camera, new file name)

    def __init__(self, camera, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.audible = False
        self._attempt = 0
        self._countdown = 0
        self._playing = False
        self.recording = False
        self._recording_when = None
        self._recording_part = 1
        self._recording_folder = None

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("CameraTile { background: black; }")
        self.video = MpvWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video)

        self._frozen = QLabel(self)
        self._frozen.setStyleSheet("background: black;")
        self._frozen.setAlignment(Qt.AlignCenter)
        self._frozen.hide()
        self._frozen_image: QImage | None = None

        self._name = QLabel(camera.name, self)
        self._name.setStyleSheet(_OVERLAY_STYLE)
        self._status = QLabel("Connecting…", self)
        self._status.setStyleSheet(_OVERLAY_STYLE)
        self._audio = QToolButton(self)
        self._audio.setText("🔇")
        self._audio.setToolTip("Play this camera's sound")
        self._audio.setStyleSheet(_OVERLAY_STYLE)
        self._audio.clicked.connect(lambda: self.audioClicked.emit(self.camera))
        self._rec = QLabel("● REC", self)
        self._rec.setStyleSheet(
            "color: #ff4444; background: rgba(0, 0, 0, 150); padding: 3px 8px; border-radius: 4px;"
        )
        self._rec.hide()

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

    def capture_to(self, path) -> bool:
        """Write the current frame to `path`. False while the stream is not playing,
        since the tile is then showing a frozen frame rather than live video."""
        if not self._playing:
            return False
        return self.video.capture_to(path)

    def clip_to(self, path, seconds: float) -> float:
        """Write the buffered last `seconds`. 0.0 while the stream is not playing."""
        if not self._playing:
            return 0.0
        return self.video.clip_to(path, seconds)

    def start_recording(self, path, when=None, part: int = 1) -> bool:
        """Begin recording to `path`.

        `when` and `part` are remembered so that a reconnect can resume into a
        NEW part instead of overwriting this file: mpv always overwrites its
        stream-record target.
        """
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

    def shutdown(self) -> None:
        self._timer.stop()
        self.video.shutdown()

    def _on_playing(self) -> None:
        self._attempt = 0
        self._playing = True
        self._timer.stop()
        self._status.hide()
        self._frozen.hide()
        self._frozen_image = None
        if self.recording and self._recording_folder is not None:
            # Playback came back while a recording was running, so the stream
            # dropped and reconnected. mpv overwrites its stream-record target,
            # so resume into a NEW part rather than destroying what was already
            # captured. On a first play `recording` is still False, so this does
            # not fire for an ordinary start.
            self._recording_part += 1
            name = recording_filename(self.camera.name, self._recording_when, self._recording_part)
            if self.video.start_recording(self._recording_folder / name):
                self.recordingResumed.emit(self.camera, name)

    def _on_failed(self, _reason: str) -> None:
        self._playing = False
        if self._timer.isActive():
            return
        if self._frozen.isHidden():
            self._frozen_image = self.video.grabFramebuffer()
            self._update_frozen_pixmap()
            self._frozen.show()
            self._frozen.raise_()
            self._place_overlays()
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

    def _update_frozen_pixmap(self) -> None:
        if self._frozen_image is None:
            return
        self._frozen.setGeometry(self.rect())
        ratio = self.devicePixelRatioF()
        target = QSize(round(self.width() * ratio), round(self.height() * ratio))
        pixmap = QPixmap.fromImage(self._frozen_image).scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        pixmap.setDevicePixelRatio(ratio)
        self._frozen.setPixmap(pixmap)

    def _place_overlays(self) -> None:
        for label in (self._name, self._status, self._audio):
            label.adjustSize()
            label.raise_()
        self._name.move(_MARGIN, _MARGIN)
        self._audio.move(self.width() - self._audio.width() - _MARGIN, _MARGIN)
        self._status.move(
            (self.width() - self._status.width()) // 2, (self.height() - self._status.height()) // 2
        )
        # Bottom-left, deliberately outside the loop above: those labels are
        # anchored to the top, and folding this in would hide it under the name.
        self._rec.adjustSize()
        self._rec.raise_()
        self._rec.move(_MARGIN, self.height() - self._rec.height() - _MARGIN)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_overlays()
        if not self._frozen.isHidden():
            self._update_frozen_pixmap()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.camera)
        super().mousePressEvent(event)
