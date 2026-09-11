from striem.audio import AudioState

A, B = "rtsp://a", "rtsp://b"


def audible(state, *urls):
    return [u for u in urls if state.is_unmuted(u)]


def test_nothing_audible_at_start():
    assert audible(AudioState(), A, B) == []


def test_toggle_unmutes_camera():
    s = AudioState()
    s.toggle(A)
    assert audible(s, A, B) == [A]


def test_toggle_other_camera_moves_sound():
    s = AudioState()
    s.toggle(A)
    s.toggle(B)
    assert audible(s, A, B) == [B]


def test_toggle_audible_camera_silences_everything():
    s = AudioState()
    s.toggle(A)
    s.toggle(A)
    assert audible(s, A, B) == []
    assert s.active is None


def test_focus_makes_camera_audible_even_when_muted():
    s = AudioState()
    s.toggle(A)
    s.toggle_mute()
    s.focus(B)
    assert audible(s, A, B) == [B]
    assert s.muted is False


def test_mute_silences_and_restores_same_camera():
    s = AudioState()
    s.toggle(A)
    s.toggle_mute()
    assert audible(s, A, B) == []
    s.toggle_mute()
    assert audible(s, A, B) == [A]


def test_mute_without_active_camera_does_nothing():
    s = AudioState()
    s.toggle_mute()
    assert s.muted is False


def test_toggle_on_active_but_muted_camera_unmutes_it():
    s = AudioState()
    s.toggle(A)
    s.toggle_mute()
    s.toggle(A)
    assert audible(s, A, B) == [A]


def test_forget_active_camera_clears_it():
    s = AudioState()
    s.toggle(A)
    s.forget(A)
    assert s.active is None
    assert audible(s, A, B) == []


def test_forget_other_camera_changes_nothing():
    s = AudioState()
    s.toggle(A)
    s.forget(B)
    assert audible(s, A, B) == [A]


def test_none_is_never_audible():
    s = AudioState()
    assert s.is_unmuted(None) is False
