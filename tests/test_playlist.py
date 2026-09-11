from pathlib import Path

from striem.playlist import Camera, load_cameras, parse_playlist

VLC_PLAYLIST = """<?xml version="1.0" encoding="UTF-8"?>
<playlist xmlns="http://xspf.org/ns/0/" xmlns:vlc="http://www.videolan.org/vlc/playlist/ns/0/" version="1">
\t<title>Playlist</title>
\t<trackList>
\t\t<track>
\t\t\t<location>rtsp://192.168.1.20:554/stream1</location>
\t\t\t<title>Front door</title>
\t\t\t<duration>0</duration>
\t\t\t<extension application="http://www.videolan.org/vlc/playlist/0">
\t\t\t\t<vlc:id>0</vlc:id>
\t\t\t\t<vlc:option>network-caching=1000</vlc:option>
\t\t\t</extension>
\t\t</track>
\t</trackList>
\t<extension application="http://www.videolan.org/vlc/playlist/0">
\t\t<vlc:item tid="0"/>
\t</extension>
</playlist>
"""


def track(location=None, title=None):
    parts = ["<track>"]
    if location is not None:
        parts.append(f"<location>{location}</location>")
    if title is not None:
        parts.append(f"<title>{title}</title>")
    parts.append("</track>")
    return "".join(parts)


def playlist(*tracks, namespace=True):
    ns = ' xmlns="http://xspf.org/ns/0/"' if namespace else ""
    return f'<?xml version="1.0"?><playlist{ns} version="1"><trackList>{"".join(tracks)}</trackList></playlist>'


def write(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def test_vlc_playlist_gives_one_camera(tmp_path):
    path = write(tmp_path, "front.xspf", VLC_PLAYLIST)
    assert parse_playlist(path) == [Camera("Front door", "rtsp://192.168.1.20:554/stream1", path)]


def test_untitled_track_uses_file_stem(tmp_path):
    path = write(tmp_path, "garage.xspf", playlist(track("rtsp://h/garage")))
    assert [c.name for c in parse_playlist(path)] == ["garage"]


def test_several_tracks_in_one_file_keep_order(tmp_path):
    path = write(tmp_path, "house.xspf", playlist(track("rtsp://h/a", "Hall"), track("rtsp://h/b", "Attic")))
    assert [(c.name, c.url) for c in parse_playlist(path)] == [("Hall", "rtsp://h/a"), ("Attic", "rtsp://h/b")]


def test_several_untitled_tracks_are_numbered(tmp_path):
    path = write(tmp_path, "yard.xspf", playlist(track("rtsp://h/1"), track("rtsp://h/2")))
    assert [c.name for c in parse_playlist(path)] == ["yard", "yard 2"]


def test_track_without_location_is_skipped(tmp_path):
    path = write(tmp_path, "x.xspf", playlist(track(title="Nothing"), track("rtsp://h/ok", "Ok")))
    assert [c.name for c in parse_playlist(path)] == ["Ok"]


def test_whitespace_around_location_and_title_is_trimmed(tmp_path):
    path = write(tmp_path, "x.xspf", playlist(track("\n  rtsp://h/cam  \n", "  Porch ")))
    camera = parse_playlist(path)[0]
    assert (camera.name, camera.url) == ("Porch", "rtsp://h/cam")


def test_playlist_without_namespace_is_read(tmp_path):
    path = write(tmp_path, "plain.xspf", playlist(track("rtsp://h/plain", "Plain"), namespace=False))
    assert [c.url for c in parse_playlist(path)] == ["rtsp://h/plain"]


def test_xml_entities_in_url_are_decoded(tmp_path):
    path = write(tmp_path, "d.xspf", playlist(track("rtsp://h/cam/realmonitor?channel=1&amp;subtype=0")))
    assert parse_playlist(path)[0].url == "rtsp://h/cam/realmonitor?channel=1&subtype=0"


def test_percent_encoding_is_kept_as_written(tmp_path):
    path = write(tmp_path, "p.xspf", playlist(track("rtsp://h/my%20cam")))
    assert parse_playlist(path)[0].url == "rtsp://h/my%20cam"


def test_malformed_file_is_reported_and_others_still_load(tmp_path):
    bad = write(tmp_path, "a-broken.xspf", "<playlist><trackList>")
    write(tmp_path, "b-good.xspf", playlist(track("rtsp://h/good", "Good")))
    cameras, errors = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["Good"]
    assert [path for path, _ in errors] == [bad]
    assert errors[0][1]


def test_duplicate_url_across_files_is_kept_once_first_wins(tmp_path):
    write(tmp_path, "a.xspf", playlist(track("rtsp://h/same", "First")))
    write(tmp_path, "b.xspf", playlist(track("rtsp://h/same", "Second")))
    cameras, _ = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["First"]


def test_files_are_read_in_case_insensitive_name_order(tmp_path):
    write(tmp_path, "b.xspf", playlist(track("rtsp://h/b", "B")))
    write(tmp_path, "A.xspf", playlist(track("rtsp://h/a", "A")))
    write(tmp_path, "c.xspf", playlist(track("rtsp://h/c", "C")))
    cameras, _ = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["A", "B", "C"]


def test_only_xspf_files_are_read_and_extension_case_is_ignored(tmp_path):
    write(tmp_path, "CAM.XSPF", playlist(track("rtsp://h/upper", "Upper")))
    write(tmp_path, "notes.txt", playlist(track("rtsp://h/txt", "Txt")))
    write(tmp_path, "list.m3u", "rtsp://h/m3u\n")
    (tmp_path / "folder.xspf").mkdir()
    cameras, errors = load_cameras(tmp_path)
    assert [c.name for c in cameras] == ["Upper"]
    assert errors == []


def test_missing_folder_gives_nothing(tmp_path):
    assert load_cameras(tmp_path / "nope") == ([], [])
