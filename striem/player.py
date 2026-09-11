"""One mpv player drawn inside a Qt widget through libmpv's OpenGL render API.

Wayland does not let mpv draw into another app's window (--wid), so mpv renders
into the QOpenGLWidget's framebuffer instead.
"""

from __future__ import annotations

import ctypes.util
import os

from PySide6.QtCore import QTimer, Signal
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

CONNECT_TIMEOUT_S = 10


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
        self._was_hidden = False
        self._player = mpv.MPV(**MPV_OPTIONS)
        self._frame_ready.connect(self.update)
        self._from_mpv.connect(self._relay)
        self._player.register_event_callback(self._on_mpv_event)
        self._player.observe_property("eof-reached", self._on_eof)
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.setInterval(CONNECT_TIMEOUT_S * 1000)
        self._watchdog.timeout.connect(self._on_watchdog)

    def play(self, url: str) -> None:
        """Start (or restart) the stream. Waits for the GL context if not shown yet."""
        self._url = url
        if self._render is not None and self._player is not None:
            self._start_playback()

    def set_muted(self, muted: bool) -> None:
        if self._player is not None:
            self._player.mute = muted

    def shutdown(self) -> None:
        """Release mpv. Call before the widget is destroyed; safe to call twice."""
        if self._player is None:
            return
        self._watchdog.stop()
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
            self._start_playback()

    def _start_playback(self) -> None:
        """The one place that starts a load: play the URL and (re)arm the watchdog."""
        self._player.play(self._url)
        self._watchdog.start()

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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._url and self._render is not None and self._player is not None and self._was_hidden:
            self._player.play(self._url)
        self._was_hidden = False

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._was_hidden = True

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
            self._watchdog.stop()
            self.playing.emit()
        else:
            self._watchdog.stop()
            self.failed.emit(detail)

    def _on_watchdog(self) -> None:
        if self._player is not None:
            self.failed.emit(f"no video within {CONNECT_TIMEOUT_S} s")
