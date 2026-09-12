from datetime import datetime
from pathlib import Path

from striem.capture import (
    capture_filename,
    capture_path,
    capture_targets,
    recording_filename,
    unique_filename,
)
from striem.playlist import Camera


def _camera(name: str) -> Camera:
    return Camera(name=name, url=f"rtsp://host/{name}", source=Path("cams.xspf"))


def test_filename_combines_timestamp_and_camera_name():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert capture_filename("Front Door", when) == "2026-09-12_143005_Front-Door.png"


def test_filename_never_contains_a_path_separator():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert capture_filename("Front/Back", when) == "2026-09-12_143005_Front-Back.png"


def test_unique_filename_suffixes_a_name_that_is_already_taken():
    taken = {"2026-09-12_143005_Cam.png"}
    assert unique_filename("2026-09-12_143005_Cam.png", taken.__contains__) == (
        "2026-09-12_143005_Cam-2.png"
    )


def test_unique_filename_keeps_counting_past_a_taken_suffix():
    taken = {"shot.png", "shot-2.png", "shot-3.png"}
    assert unique_filename("shot.png", taken.__contains__) == "shot-4.png"


def test_capture_targets_is_the_focused_camera_alone():
    cameras = [_camera("a"), _camera("b"), _camera("c")]
    assert capture_targets(cameras, cameras[1].url) == [cameras[1]]


def test_capture_targets_is_every_camera_when_none_is_focused():
    cameras = [_camera("a"), _camera("b"), _camera("c")]
    assert capture_targets(cameras, None) == cameras


def test_capture_path_joins_the_folder_and_the_generated_name(tmp_path):
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert capture_path(tmp_path, "Front Door", when) == tmp_path / "2026-09-12_143005_Front-Door.png"


def test_capture_path_steps_past_a_file_already_on_disk(tmp_path):
    when = datetime(2026, 9, 12, 14, 30, 5)
    (tmp_path / "2026-09-12_143005_Cam.png").touch()
    assert capture_path(tmp_path, "Cam", when) == tmp_path / "2026-09-12_143005_Cam-2.png"


def test_filename_takes_an_extension():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert capture_filename("Front Door", when, ".mkv") == "2026-09-12_143005_Front-Door.mkv"


def test_capture_path_carries_the_extension(tmp_path):
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert capture_path(tmp_path, "Cam", when, ".mkv") == tmp_path / "2026-09-12_143005_Cam.mkv"


def test_recording_filename_marks_a_recording():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert recording_filename("Front Door", when) == "2026-09-12_143005_Front-Door-rec.mkv"


def test_recording_filename_numbers_later_parts():
    when = datetime(2026, 9, 12, 14, 30, 5)
    assert recording_filename("Cam", when, part=2) == "2026-09-12_143005_Cam-rec2.mkv"
    assert recording_filename("Cam", when, part=3) == "2026-09-12_143005_Cam-rec3.mkv"
