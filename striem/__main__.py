"""Entry point: `striem` or `python -m striem`."""

from __future__ import annotations

import argparse
import locale
import sys

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from striem.version import title

HELP = """\
keys:
  1-9, Esc    focus a camera, back to the grid
  M           mute
  S           save a frame
  C           save the last 30 seconds
  R           start or stop recording
  F11         fullscreen

folders:
  playlists   ~/Videos/Cameras   change with ⋮ → Choose folder…
  captures    ~/Videos/Striem    change with ⋮ → Capture folder…
"""


def parse_args(argv: list[str]) -> list[str]:
    """Handle --help and --version; return the remaining arguments for Qt."""
    parser = argparse.ArgumentParser(
        prog="striem",
        description="Watch the RTSP cameras listed in a folder of .xspf playlists.",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=title())
    # parse_known_args, so Qt's own flags such as -platform still reach Qt.
    return parser.parse_known_args(argv[1:])[1]


def create_app(argv: list[str]) -> QApplication:
    # Must happen before QApplication exists; libmpv's GL renderer wants a core profile.
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(argv)
    app.setApplicationName("Striem")
    app.setDesktopFileName("io.github.striem.Striem")
    # Qt resets the C locale; libmpv requires LC_NUMERIC=C.
    locale.setlocale(locale.LC_NUMERIC, "C")
    return app


def main() -> int:
    qt_args = parse_args(sys.argv)
    app = create_app(sys.argv[:1] + qt_args)
    from striem.settings import Settings
    from striem.window import MainWindow

    window = MainWindow(Settings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
