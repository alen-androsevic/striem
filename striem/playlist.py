"""Read camera streams from the .xspf playlists in a folder."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Camera:
    name: str
    url: str
    source: Path


def load_cameras(folder: Path) -> tuple[list[Camera], list[tuple[Path, str]]]:
    """All cameras from the folder's .xspf files, plus (file, message) for files that failed.

    Files are read in case-insensitive name order; a URL seen twice is kept once (first wins, within or across files).
    """
    cameras: list[Camera] = []
    errors: list[tuple[Path, str]] = []
    if not folder.is_dir():
        return cameras, errors
    seen: set[str] = set()
    for path in playlist_files(folder):
        try:
            found = parse_playlist(path)
        except (ET.ParseError, OSError, ValueError, LookupError) as exc:
            errors.append((path, str(exc)))
            continue
        for camera in found:
            if camera.url not in seen:
                seen.add(camera.url)
                cameras.append(camera)
    return cameras, errors


def playlist_files(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.suffix.lower() == ".xspf" and p.is_file()]
    return sorted(files, key=lambda p: p.name.lower())


def parse_playlist(path: Path) -> list[Camera]:
    """One Camera per <track> with a <location>. Works with or without the XSPF namespace."""
    root = ET.parse(path).getroot()
    cameras: list[Camera] = []
    untitled = 0
    for track in (el for el in root.iter() if _local(el.tag) == "track"):
        url = _child_text(track, "location")
        if not url:
            continue
        name = _child_text(track, "title")
        if not name:
            untitled += 1
            name = path.stem if untitled == 1 else f"{path.stem} {untitled}"
        cameras.append(Camera(name=name, url=url, source=path))
    return cameras


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local(child.tag) == name and child.text:
            return child.text.strip()
    return ""
