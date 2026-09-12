"""Dev tool: run Striem on a folder, drive it with scripted steps, save screenshots.

Usage: .venv/bin/python scripts/snapshot.py --folder DIR --out DIR STEP...
Steps: wait:SECONDS  shot:NAME  focus:N  grid  audio:N  mute  state  capture  clip   (N is 1-based)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from striem.__main__ import create_app  # noqa: E402


class FixedFolder:
    def __init__(self, folder: Path, captures: Path):
        self._folder = folder
        self._captures = captures
        self._clip_seconds = 30

    def folder(self) -> Path:
        return self._folder

    def set_folder(self, folder: Path) -> None:
        self._folder = folder

    def capture_folder(self) -> Path:
        return self._captures

    def set_capture_folder(self, folder: Path) -> None:
        self._captures = folder

    def clip_seconds(self) -> int:
        return self._clip_seconds

    def set_clip_seconds(self, seconds: int) -> None:
        self._clip_seconds = seconds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("steps", nargs="+")
    args = parser.parse_args()

    app = create_app(sys.argv[:1])
    from striem.window import MainWindow

    window = MainWindow(FixedFolder(args.folder, args.out))
    window.show()
    args.out.mkdir(parents=True, exist_ok=True)
    steps = list(args.steps)

    def run_next() -> None:
        if not steps:
            window.close()
            app.quit()
            return
        step = steps.pop(0)
        command, _, arg = step.partition(":")
        delay_ms = 0
        if command == "wait":
            delay_ms = int(float(arg) * 1000)
        elif command == "shot":
            path = args.out / f"{arg}.png"
            window.grab().save(str(path))
            print("saved", path, flush=True)
        elif command == "focus":
            window.focus_index(int(arg) - 1)
        elif command == "grid":
            window.show_grid()
        elif command == "audio":
            window.toggle_audio_index(int(arg) - 1)
        elif command == "mute":
            window.toggle_mute()
        elif command == "capture":
            for path in window.capture():
                print("captured", path, flush=True)
        elif command == "clip":
            for path in window.clip():
                print("clipped", path, flush=True)
        elif command == "state":
            for tile in window.tiles():
                print(
                    f"{tile.camera.name}: audible={tile.audible} visible={tile.isVisible()} "
                    f"status={tile.status_text()!r}",
                    flush=True,
                )
        else:
            raise SystemExit(f"unknown step: {step}")
        QTimer.singleShot(delay_ms, run_next)

    QTimer.singleShot(0, run_next)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
