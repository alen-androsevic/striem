import striem
from striem.version import CHANNELS, channel, title


def stamp(tmp_path, text):
    path = tmp_path / "CHANNEL"
    path.write_text(text)
    return path


def test_both_channels_are_reported(tmp_path):
    for name in CHANNELS:
        assert channel(stamp(tmp_path, name)) == name


def test_a_trailing_newline_is_tolerated(tmp_path):
    # CI writes the file with echo, so it ends in a newline.
    assert channel(stamp(tmp_path, "nightly\n")) == "nightly"


def test_no_stamp_means_a_source_build(tmp_path):
    assert channel(tmp_path / "absent") == "dev"


def test_an_unrecognised_channel_is_not_trusted(tmp_path):
    # Whatever the file holds ends up in the window title, so only accept known names.
    assert channel(stamp(tmp_path, "beta")) == "dev"


def test_an_empty_stamp_is_not_a_channel(tmp_path):
    assert channel(stamp(tmp_path, "\n")) == "dev"


def test_title_names_the_channel_and_the_version(tmp_path):
    assert title(stamp(tmp_path, "stable")) == f"Striem stable-{striem.__version__}"
    assert title(stamp(tmp_path, "nightly")) == f"Striem nightly-{striem.__version__}"


def test_title_says_dev_without_a_stamp(tmp_path):
    assert title(tmp_path / "absent") == f"Striem dev-{striem.__version__}"
