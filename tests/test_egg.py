from PySide6.QtCore import Qt

from striem.egg import BONUS_CAMERA, KONAMI, CodeDetector

OTHER = int(Qt.Key_Z)


def feed_all(detector, keys):
    return [detector.feed(key) for key in keys]


def test_the_code_fires_on_its_last_key_only():
    results = feed_all(CodeDetector(), KONAMI)
    assert results[-1] is True
    assert not any(results[:-1])


def test_an_almost_complete_code_does_not_fire():
    keys = list(KONAMI[:-1]) + [OTHER]
    assert not any(feed_all(CodeDetector(), keys))


def test_a_repeated_prefix_does_not_wedge_progress():
    # Three ups: the last two are still a valid start, so the code completes.
    detector = CodeDetector()
    keys = [int(Qt.Key_Up), *KONAMI]
    assert feed_all(detector, keys)[-1] is True


def test_noise_before_the_code_is_ignored():
    keys = list(KONAMI[:4]) + [OTHER] + list(KONAMI)
    assert feed_all(CodeDetector(), keys)[-1] is True


def test_it_can_fire_again_after_firing():
    detector = CodeDetector()
    assert feed_all(detector, KONAMI)[-1] is True
    assert feed_all(detector, KONAMI)[-1] is True


def test_nothing_fires_before_enough_keys():
    assert not any(feed_all(CodeDetector(), KONAMI[:-1]))


def test_bonus_camera_streams_over_a_protocol_mpv_handles():
    # No yt-dlp in the Flatpak, so the URL has to be one ffmpeg opens directly.
    assert BONUS_CAMERA.url.startswith("https://")
    assert BONUS_CAMERA.url.endswith(".m3u8")
    assert BONUS_CAMERA.name
