from pathlib import Path

import pytest

from striem.layout import diff_cameras, grid_dims
from striem.playlist import Camera


def cam(name, url):
    return Camera(name, url, Path(f"{name}.xspf"))


@pytest.mark.parametrize(
    "n, dims",
    [(0, (0, 0)), (1, (1, 1)), (2, (2, 1)), (3, (2, 2)), (4, (2, 2)), (5, (3, 2)),
     (6, (3, 2)), (7, (3, 3)), (9, (3, 3)), (10, (4, 3)), (13, (4, 4))],
)
def test_grid_dims(n, dims):
    assert grid_dims(n) == dims


def test_diff_splits_added_removed_kept():
    a, b, c = cam("a", "rtsp://a"), cam("b", "rtsp://b"), cam("c", "rtsp://c")
    added, removed, kept = diff_cameras([a, b], [b, c])
    assert added == [c]
    assert removed == [a]
    assert kept == [b]


def test_diff_keeps_camera_whose_title_changed_and_returns_new_object():
    old = cam("Old name", "rtsp://x")
    new = cam("New name", "rtsp://x")
    added, removed, kept = diff_cameras([old], [new])
    assert (added, removed) == ([], [])
    assert kept[0].name == "New name"


def test_diff_orders_follow_their_lists():
    a, b, c, d = (cam(n, f"rtsp://{n}") for n in "abcd")
    added, removed, _ = diff_cameras([d, c], [b, a])
    assert added == [b, a]
    assert removed == [d, c]


def test_diff_from_empty_adds_everything():
    a, b = cam("a", "rtsp://a"), cam("b", "rtsp://b")
    assert diff_cameras([], [a, b]) == ([a, b], [], [])
