import pytest

from striem.player import CONNECT_TIMEOUT_S, MPV_OPTIONS
from striem.tile import reconnect_delay


@pytest.mark.parametrize("attempt, seconds", [(0, 2), (1, 4), (2, 8), (3, 16), (4, 30), (5, 30), (50, 30)])
def test_reconnect_backoff(attempt, seconds):
    assert reconnect_delay(attempt) == seconds


def test_mpv_options_match_spec():
    assert MPV_OPTIONS == {
        "vo": "libmpv",
        "profile": "low-latency",
        "rtsp_transport": "tcp",
        "cache": "no",
        "hwdec": "auto-copy-safe",
        "keep_open": "yes",
        "mute": "yes",
    }


def test_connect_timeout_matches_spec():
    assert CONNECT_TIMEOUT_S == 10
