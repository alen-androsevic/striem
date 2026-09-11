"""Which camera is audible: at most one at a time, anywhere in the app."""

from __future__ import annotations


class AudioState:
    """A camera (by URL) is audible iff it is `active` and `muted` is off."""

    def __init__(self) -> None:
        self.active: str | None = None
        self.muted = False

    def is_unmuted(self, url: str | None) -> bool:
        return url is not None and url == self.active and not self.muted

    def toggle(self, url: str) -> None:
        """Tile speaker button: silence this camera if audible, else make it the audible one."""
        if self.is_unmuted(url):
            self.active = None
        else:
            self.active = url
            self.muted = False

    def focus(self, url: str) -> None:
        self.active = url
        self.muted = False

    def toggle_mute(self) -> None:
        """The M key: mute/unmute the remembered camera. No-op without one."""
        if self.active is not None:
            self.muted = not self.muted

    def forget(self, url: str) -> None:
        """The camera left the folder."""
        if self.active == url:
            self.active = None
