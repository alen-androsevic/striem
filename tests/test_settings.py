from pathlib import Path

from striem.settings import DEFAULT_CAPTURE_FOLDER, DEFAULT_FOLDER


def test_default_playlist_folder_matches_spec():
    assert DEFAULT_FOLDER == Path.home() / "Videos" / "Cameras"


def test_default_capture_folder_matches_spec():
    assert DEFAULT_CAPTURE_FOLDER == Path.home() / "Pictures" / "Striem"
