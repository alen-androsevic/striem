"""Grid sizing and working out which camera tiles change after a rescan."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from striem.playlist import Camera


def grid_dims(n: int) -> tuple[int, int]:
    """(cols, rows) for n tiles: as square as possible, wider than tall."""
    if n <= 0:
        return 0, 0
    cols = math.ceil(math.sqrt(n))
    return cols, math.ceil(n / cols)


def diff_cameras(
    old: Sequence[Camera], new: Sequence[Camera]
) -> tuple[list[Camera], list[Camera], list[Camera]]:
    """(added, removed, kept), matched by URL. kept holds the new objects so renamed titles show."""
    old_urls = {c.url for c in old}
    new_urls = {c.url for c in new}
    added = [c for c in new if c.url not in old_urls]
    removed = [c for c in old if c.url not in new_urls]
    kept = [c for c in new if c.url in old_urls]
    return added, removed, kept
