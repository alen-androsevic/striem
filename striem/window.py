"""Main window: camera grid, focus mode, toolbar, shortcuts and folder watching."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from striem.audio import AudioState
from striem.capture import capture_path, capture_targets, recording_filename, unique_filename
from striem.egg import BONUS_CAMERA, CodeDetector
from striem.layout import diff_cameras, grid_dims
from striem.playlist import Camera, load_cameras
from striem.tile import CameraTile
from striem.version import title

RESCAN_DEBOUNCE_MS = 500


def _pretty(folder: Path) -> str:
    home = str(Path.home())
    text = str(folder)
    return "~" + text[len(home):] if text.startswith(home) else text


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle(title())
        self.resize(1280, 760)
        self._settings = settings
        self._folder: Path = settings.folder()
        self._cameras: list[Camera] = []
        self._tiles: dict[str, CameraTile] = {}
        self._focused: str | None = None
        # Frozen when recording starts; navigation never rewrites it.
        self._recording: list[Camera] = []
        self._audio = AudioState()
        self._camera_actions: list[QAction] = []
        self._bonus: list[Camera] = []
        self._konami = CodeDetector()

        self._build_toolbar()
        self._build_pages()
        self._build_shortcuts()

        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(RESCAN_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.rescan)
        self._watcher.directoryChanged.connect(self._debounce.start)
        self._watcher.fileChanged.connect(self._debounce.start)

        self.rescan()

    # Public API (also used by scripts/snapshot.py)

    def rescan(self) -> None:
        cameras, errors = load_cameras(self._folder)
        known = {camera.url for camera in cameras}
        cameras += [camera for camera in self._bonus if camera.url not in known]
        added, removed, kept = diff_cameras(self._cameras, cameras)
        for camera in removed:
            tile = self._tiles.pop(camera.url)
            self._audio.forget(camera.url)
            if self._focused == camera.url:
                self._focused = None
            # Its tile is about to be destroyed, so drop it from the locked set;
            # otherwise a later stop would address a tile that no longer exists.
            self._recording = [c for c in self._recording if c.url != camera.url]
            self._grid.removeWidget(tile)
            tile.shutdown()
            tile.deleteLater()
        for camera in kept:
            self._tiles[camera.url].set_camera(camera)
        for camera in added:
            tile = CameraTile(camera, self._grid_page)
            tile.clicked.connect(self._on_tile_clicked)
            tile.audioClicked.connect(self._on_audio_clicked)
            tile.recordingResumed.connect(self._on_recording_resumed)
            self._tiles[camera.url] = tile
        self._cameras = cameras
        self._watch_folder()
        self._rebuild_camera_actions()
        self._relayout()
        self._apply_audio()
        self._show_errors(errors)

    def focus_index(self, index: int) -> None:
        if 0 <= index < len(self._cameras):
            self._focus(self._cameras[index].url)

    def show_grid(self) -> None:
        # Only when leaving focus: Esc in the grid must not silence a camera
        # the user unmuted with its speaker button.
        if self._focused is None:
            return
        self._focused = None
        self._audio.silence()
        self._relayout()
        self._apply_audio()

    def toggle_audio_index(self, index: int) -> None:
        if 0 <= index < len(self._cameras):
            self._audio.toggle(self._cameras[index].url)
            self._apply_audio()

    def toggle_mute(self) -> None:
        self._audio.toggle_mute()
        self._apply_audio()

    def capture(self) -> list[Path]:
        """Save a frame from the focused camera, or from every camera in the grid."""
        targets = capture_targets(self._cameras, self._focused)
        if not targets:
            self.statusBar().showMessage("No cameras to capture", 5000)
            return []
        folder = self._settings.capture_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not save to {_pretty(folder)}: {exc}", 5000)
            return []
        # One timestamp for the whole burst, so a grid capture groups together.
        when = datetime.now()
        saved: list[Path] = []
        skipped = 0
        for camera in targets:
            tile = self._tiles.get(camera.url)
            if tile is None:
                continue
            path = capture_path(folder, camera.name, when)
            if tile.capture_to(path):
                saved.append(path)
            else:
                skipped += 1
        self._report_capture(saved, skipped, folder)
        return saved

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
        # One timestamp for the whole burst, so a grid clip groups together.
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

    def toggle_recording(self) -> bool:
        """Start recording the cameras on screen, or stop whatever is recording."""
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()
        # Sync the toolbar to what is actually happening, on every path. Clicking
        # a checkable action toggles it before this runs, so a failed start would
        # otherwise leave the toolbar showing a recording that never began.
        recording = bool(self._recording)
        self._record_action.setChecked(recording)
        return recording

    def _start_recording(self) -> None:
        targets = capture_targets(self._cameras, self._focused)
        if not targets:
            self.statusBar().showMessage("No cameras to record", 5000)
            return
        folder = self._settings.capture_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not save to {_pretty(folder)}: {exc}", 5000)
            return
        when = datetime.now()
        started: list[Camera] = []
        for camera in targets:
            tile = self._tiles.get(camera.url)
            if tile is None:
                continue
            name = recording_filename(camera.name, when)
            path = folder / unique_filename(name, lambda c: (folder / c).exists())
            if tile.start_recording(path, when):
                started.append(camera)
        if not started:
            self.statusBar().showMessage("Could not start recording", 5000)
            return
        # The set is locked here: changing view never changes what is recording.
        self._recording = started
        plural = "s" if len(started) > 1 else ""
        self.statusBar().showMessage(
            f"Recording {len(started)} camera{plural} to {_pretty(folder)}", 5000
        )

    def _stop_recording(self) -> None:
        stopped = 0
        for camera in self._recording:
            tile = self._tiles.get(camera.url)
            if tile is not None:
                tile.stop_recording()
                stopped += 1
        self._recording = []
        self.statusBar().showMessage(f"Stopped recording {stopped} cameras", 5000)

    def tiles(self) -> list[CameraTile]:
        return [self._tiles[c.url] for c in self._cameras]

    # Building the UI

    def _build_toolbar(self) -> None:
        self._toolbar = QToolBar("Cameras", self)
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)
        self._all_action = QAction("All", self)
        self._all_action.triggered.connect(self.show_grid)
        self._mute_action = QAction("Mute", self)
        self._mute_action.setCheckable(True)
        self._mute_action.triggered.connect(self.toggle_mute)
        self._capture_action = QAction("Capture", self)
        self._capture_action.setToolTip("Save a frame from the cameras on screen (S)")
        self._capture_action.triggered.connect(self.capture)
        self._clip_action = QAction("Clip", self)
        self._clip_action.setToolTip("Save the buffered last seconds (C)")
        self._clip_action.triggered.connect(self.clip)
        self._record_action = QAction("Record", self)
        self._record_action.setCheckable(True)
        self._record_action.setToolTip("Record the cameras on screen until stopped (R)")
        self._record_action.triggered.connect(self.toggle_recording)
        self._folder_action = QAction("Choose folder…", self)
        self._folder_action.triggered.connect(self._choose_folder)
        self._capture_folder_action = QAction("Capture folder…", self)
        self._capture_folder_action.triggered.connect(self._choose_capture_folder)
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._toolbar.addAction(self._all_action)
        self._camera_anchor = self._toolbar.addSeparator()
        self._toolbar.addWidget(spacer)
        self._toolbar.addAction(self._capture_action)
        self._toolbar.addAction(self._clip_action)
        self._toolbar.addAction(self._record_action)
        self._toolbar.addAction(self._mute_action)
        self._toolbar.addAction(self._folder_action)
        self._toolbar.addAction(self._capture_folder_action)

    def _build_pages(self) -> None:
        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        self._grid_page = QWidget(self._stack)
        self._grid_page.setStyleSheet("background: #111;")
        self._grid = QGridLayout(self._grid_page)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(2)
        self._stack.addWidget(self._grid_page)

        self._empty_page = QWidget(self._stack)
        empty_layout = QVBoxLayout(self._empty_page)
        empty_layout.addStretch()
        self._empty_label = QLabel(self._empty_page)
        empty_layout.addWidget(self._empty_label, alignment=Qt.AlignCenter)
        choose = QPushButton("Choose folder…", self._empty_page)
        choose.clicked.connect(self._choose_folder)
        empty_layout.addWidget(choose, alignment=Qt.AlignCenter)
        empty_layout.addStretch()
        self._stack.addWidget(self._empty_page)

    def _build_shortcuts(self) -> None:
        for number in range(1, 10):
            QShortcut(QKeySequence(str(number)), self, activated=lambda i=number - 1: self.focus_index(i))
        QShortcut(QKeySequence("0"), self, activated=self.show_grid)
        QShortcut(QKeySequence("Esc"), self, activated=self.show_grid)
        QShortcut(QKeySequence("M"), self, activated=self.toggle_mute)
        QShortcut(QKeySequence("S"), self, activated=self.capture)
        QShortcut(QKeySequence("C"), self, activated=self.clip)
        QShortcut(QKeySequence("R"), self, activated=self.toggle_recording)
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)

    # Keeping the UI in sync

    def _rebuild_camera_actions(self) -> None:
        for action in self._camera_actions:
            self._toolbar.removeAction(action)
            action.deleteLater()
        self._camera_actions = []
        for index, camera in enumerate(self._cameras):
            action = QAction(camera.name, self)
            if index < 9:
                action.setToolTip(f"{camera.name} (key {index + 1})")
            action.triggered.connect(lambda _=False, url=camera.url: self._focus(url))
            self._toolbar.insertAction(self._camera_anchor, action)
            self._camera_actions.append(action)

    def _relayout(self) -> None:
        grid = self._grid
        while grid.count():
            grid.takeAt(0)
        for row in range(grid.rowCount()):
            grid.setRowStretch(row, 0)
        for col in range(grid.columnCount()):
            grid.setColumnStretch(col, 0)

        if not self._cameras:
            self._empty_label.setText(f"No .xspf playlists in {_pretty(self._folder)}")
            self._stack.setCurrentWidget(self._empty_page)
            return
        self._stack.setCurrentWidget(self._grid_page)

        if self._focused is not None:
            # Hide the others instead of reparenting: moving a QOpenGLWidget recreates its GL context.
            for url, tile in self._tiles.items():
                tile.setVisible(url == self._focused)
            grid.addWidget(self._tiles[self._focused], 0, 0)
            grid.setRowStretch(0, 1)
            grid.setColumnStretch(0, 1)
            return

        cols, rows = grid_dims(len(self._cameras))
        for index, camera in enumerate(self._cameras):
            tile = self._tiles[camera.url]
            grid.addWidget(tile, index // cols, index % cols)
            tile.show()
        for row in range(rows):
            grid.setRowStretch(row, 1)
        for col in range(cols):
            grid.setColumnStretch(col, 1)

    def _apply_audio(self) -> None:
        for url, tile in self._tiles.items():
            tile.set_audible(self._audio.is_unmuted(url))
        self._mute_action.setChecked(self._audio.muted)

    def _report_capture(self, saved: list[Path], skipped: int, folder: Path) -> None:
        if not saved:
            self.statusBar().showMessage("Nothing to save: no camera is playing", 5000)
            return
        what = saved[0].name if len(saved) == 1 else f"{len(saved)} frames"
        note = f" ({skipped} not playing)" if skipped else ""
        self.statusBar().showMessage(f"Saved {what} to {_pretty(folder)}{note}", 5000)

    def _report_clip(self, saved: list[Path], seconds: float, folder: Path) -> None:
        # Reports the duration actually written, not the length requested: the
        # buffer is sized in bytes, so it may not reach back the full N seconds.
        if not saved:
            self.statusBar().showMessage("Nothing buffered to clip yet", 5000)
            return
        what = saved[0].name if len(saved) == 1 else f"{len(saved)} clips"
        self.statusBar().showMessage(f"Saved {what} ({seconds:.0f}s) to {_pretty(folder)}", 5000)

    def _show_errors(self, errors: list[tuple[Path, str]]) -> None:
        if errors:
            names = ", ".join(path.name for path, _ in errors)
            self.statusBar().showMessage(f"Could not read: {names}")
        else:
            self.statusBar().clearMessage()

    def _watch_folder(self) -> None:
        watched = self._watcher.directories() + self._watcher.files()
        if watched:
            self._watcher.removePaths(watched)
        if self._folder.is_dir():
            self._watcher.addPath(str(self._folder))
            files = [str(p) for p in self._folder.iterdir() if p.suffix.lower() == ".xspf"]
            if files:
                self._watcher.addPaths(files)

    # Reacting to the user

    def _focus(self, url: str) -> None:
        self._focused = url
        self._audio.focus(url)
        self._relayout()
        self._apply_audio()

    def _on_tile_clicked(self, camera: Camera) -> None:
        if self._focused == camera.url:
            self.show_grid()
        else:
            self._focus(camera.url)

    def _on_audio_clicked(self, camera: Camera) -> None:
        self._audio.toggle(camera.url)
        self._apply_audio()

    def _on_recording_resumed(self, camera: Camera, name: str) -> None:
        self.statusBar().showMessage(
            f"{camera.name} reconnected — recording continues in {name}", 5000
        )

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose camera playlist folder", str(self._folder))
        if not chosen:
            return
        self._folder = Path(chosen)
        self._settings.set_folder(self._folder)
        self._focused = None
        self.rescan()

    def _choose_capture_folder(self) -> None:
        current = self._settings.capture_folder()
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose folder for captured frames", str(current)
        )
        if chosen:
            self._settings.set_capture_folder(Path(chosen))

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event) -> None:
        # Arrows, B and A are the only keys with no shortcut, so the code can be
        # typed without tripping focus, mute or fullscreen on the way through.
        if self._konami.feed(event.key()) and not self._bonus:
            self._bonus = [BONUS_CAMERA]
            self.rescan()
            self.statusBar().showMessage(f"{BONUS_CAMERA.name} joined the grid", 5000)
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        # Stop first so mpv finalises each container. Shutting the player down
        # mid-recording leaves a file that will not play.
        if self._recording:
            self._stop_recording()
        for tile in self._tiles.values():
            tile.shutdown()
        super().closeEvent(event)
