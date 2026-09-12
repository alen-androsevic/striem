"""Which build is this? The title bar answers it, so a tester can say what they have."""

from __future__ import annotations

from pathlib import Path

from striem import __version__

CHANNELS = ("stable", "nightly")
CHANNEL_FILE = Path(__file__).with_name("CHANNEL")


def channel(path: Path | None = None) -> str:
    """The release channel this copy came from, or "dev" when it cannot be known.

    Stable and nightly are built from one manifest and are otherwise identical,
    so CI stamps CHANNEL into the package at build time. A build from source has
    no such file and says "dev" rather than claiming a channel it is not from.
    """
    try:
        name = (CHANNEL_FILE if path is None else path).read_text().strip()
    except OSError:
        return "dev"
    # Only ever show a channel we recognise: this string goes in the title bar.
    return name if name in CHANNELS else "dev"


def title(path: Path | None = None) -> str:
    return f"Striem {channel(path)}-{__version__}"
