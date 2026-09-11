"""Entry point: `striem` or `python -m striem`."""

from __future__ import annotations

import locale
import sys

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication


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
    app = create_app(sys.argv)
    from striem.settings import Settings
    from striem.window import MainWindow

    window = MainWindow(Settings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
