# Striem — retroactive clips and start/stop recording

Date: 2026-09-12
Status: approved design, pending spec review

## Goal

Two ways to keep video, alongside the still-frame capture already built:

- **Clip** (`C`): save the last N seconds that already happened, retroactively.
- **Record** (`R`): start writing from now until stopped.

Both build on the capture feature: they reuse its target-selection rule, its
naming helpers and its folder setting.

## Decisions

| Question | Decision |
|---|---|
| Which modes | Both retroactive clip and start/stop recording |
| What one press covers | Context-sensitive, exactly like the capture key: focused → that camera, grid → all |
| View change mid-recording | The recording set is locked at start; navigation never changes it |
| Where files go | One shared capture folder for stills and clips, default `~/Videos/Striem` |
| Buffer | Always on, 30 s clip length, configurable |

## Verified findings

Measured against a local mediamtx with ffmpeg test streams (640x360, h264+aac),
using mpv 0.41 and python-mpv 1.0.8. These justify the design and are not
assumptions:

- `profile=low-latency` does **not** set `cache=no`. That was the app's own
  separate choice, so a back buffer does not contradict the profile.
- With `cache=yes` and a back buffer the stream stays at the live edge: forward
  cache duration measured 0.24 s, forward bytes ~19 KB.
- Back buffer cost measured ~80 KB/s per camera at 640x360 (1.2 MB per 15 s).
- `demuxer-lavf-probe-info=nostreams`, set by the low-latency profile, is the
  **single** reason container writing fails. With it, both `dump-cache` and
  `stream-record` produce 0-byte files. Overriding just that option to `yes`
  makes both produce valid h264+aac files. `analyzeduration` is unrelated:
  overriding it alone does not help.
- The override costs no measurable startup latency: 1.56 s vs 1.57 s minimum
  across three runs each.
- A **bounded** `dump-cache start end file` returns in ~0 s and writes a valid,
  correctly-bounded clip (a 10 s request produced 10.488 s, 465 KB).
- `dump-cache` with `end="no"` on a live stream **never terminates**: it keeps
  writing as the cache grows and blocks the caller. The end must always be
  bounded.
- mpv offers **no time-based back buffer**. `--demuxer-max-back-bytes` is a
  byte size; `--cache-secs` is forward-only. A clip length in seconds is
  therefore a dump-request window, not a buffer setting.

## Stream configuration

`MPV_OPTIONS` changes, pinned by `test_tile.py::test_mpv_options_match_spec`,
which moves in the same commit:

```
  cache: "no"                    ->  "yes"
+ demuxer_lavf_probe_info: "yes"
+ demuxer_max_back_bytes: "32MiB"
```

Everything else is unchanged: `vo=libmpv`, `profile=low-latency`,
`rtsp_transport=tcp`, `hwdec=auto-copy-safe`, `keep_open=yes`, `mute=yes`.
`demuxer_max_bytes` is deliberately not set: forward usage measured 19 KB, so
the 150 MiB default is never approached.

**Buffer capacity and clip length are separate.** Capacity is internal and in
bytes: 32 MiB per camera, a bounded 192 MiB ceiling for six cameras, and far
less in practice (a 640x360 stream used ~2.4 MB per 30 s). Clip length N is the
user-facing setting, default 30 s, and is the dump request window
`[pos - N, pos]`. If a high-bitrate camera means 32 MiB held less than N
seconds, the clip is shorter and the status message reports the duration
actually written.

## Components

| File | Additions |
|---|---|
| `striem/capture.py` | `extension=".png"` parameter on `capture_filename` and `capture_path`; `recording_filename(name, when, part)` producing the `-rec` / `-rec2` marker. `capture_targets` is reused unchanged for all three actions. |
| `striem/player.py` | `clip_to(path, seconds)` issuing a bounded `dump-cache`; `start_recording(path)` and `stop_recording()` setting and clearing the `stream_record` property. |
| `striem/tile.py` | Same three, guarded on `self._playing` as `capture_to` already is; a steady red `REC` overlay. |
| `striem/window.py` | `C` and `R` shortcuts, `Clip` and checkable `Record` toolbar actions, `self._recording` holding the locked set, status reporting. |
| `striem/settings.py` | `DEFAULT_CAPTURE_FOLDER` becomes `~/Videos/Striem`; `clip_seconds()` / `set_clip_seconds()`, default 30. |

## Behaviour

### Clip (`C`)

Same shape as the existing capture path: select targets with
`capture_targets(cameras, focused)`, create the folder, take one timestamp for
the whole burst, then per camera issue `dump-cache [pos - N, pos]` into
`capture_path(folder, name, when, ".mkv")`. The status message reports the
duration actually written, not the requested N.

### Record (`R`)

Idle: compute targets with the same function, **freeze that list** into
`self._recording`, and arm each tile. Active: stop exactly the frozen list,
clear the state, report. View changes never consult the frozen list, which is
what makes the set locked at start.

Each recording is named with `recording_filename(...)` and then passed through
`unique_filename` against the folder, exactly as clips and stills are. A
recording's file exists from the moment it is armed, so the disk check is
meaningful and a clip taken in the same second as a recording of the same
camera cannot collide with it.

If `stream-record` fails to arm for every target, the app does not enter the
recording state at all, so the toolbar never shows recording that is not
happening.

### Edge cases

- **A camera removed by a playlist rescan while recording.** Its tile is
  destroyed, so it is also dropped from the frozen set; otherwise a later stop
  would address a tile that no longer exists.
- **A stream dropping mid-recording.** mpv overwrites the `stream-record` file,
  so re-arming after the tile's existing reconnect with the same path would
  destroy what was already captured. Recording resumes into a new part file
  (`-rec2`, `-rec3`, …) and the status bar says so. This honours locked-at-start
  without silent data loss.
- **Quitting while recording.** `closeEvent` currently calls `tile.shutdown()`
  directly. Recordings must be stopped first so mpv finalises each container;
  otherwise a normal quit produces unplayable files.
- **Pressing `C` while recording.** The two are independent and may run at
  once: a clip dumps the back buffer to its own file and does not touch the
  `stream-record` property, so an in-progress recording is unaffected.

## UI

The toolbar becomes:

```
All | cameras | ... | Capture  Clip  Record | Mute | (overflow)
```

The three capture actions are grouped, and the two folder choosers move into an
overflow menu button. This regrouping is scoped to the crowding this feature
causes: seven right-hand controls otherwise. `Record` is checkable, like `Mute`,
so the toolbar shows that recording is live.

The overflow menu also carries `Clip length…`, a plain integer prompt writing
`clip_seconds`. Without it the setting would be unreachable state that only a
hand-edited QSettings store could change.

Each recording tile shows a steady red dot with `REC`, placed bottom-left to
clear the existing name (top-left), speaker (top-right) and status (centre)
overlays. Steady rather than blinking: a blink needs a per-tile timer for no
information gain.

Status messages follow the existing 5-second pattern:

- `Saved 18s clip from Front Door to ~/Videos/Striem`
- `Recording 4 cameras to ~/Videos/Striem` / `Stopped recording 4 cameras`
- `Front Door reconnected — recording continues in ...-rec2.mkv`

## Error handling

Every failure degrades to a status message rather than an exception, reusing
the guarded-write path built for stills: an unwritable folder, `dump-cache`
refusing for one camera, a camera that is not playing (skipped, as stills are),
and `stream-record` failing to arm.

## Packaging

```
  - --filesystem=home:ro
- - --filesystem=xdg-pictures:create
+ - --filesystem=xdg-videos/Striem:create
```

The subpath grant covers exactly the capture folder. A plain `xdg-videos` grant
would give write access to all of `~/Videos`, which contains the
`~/Videos/Cameras` playlist folder the app otherwise only reads through
`home:ro`; the app should not be able to write its own input. This grant is
strictly narrower than the `xdg-pictures:create` it replaces.

A capture folder configured outside the default still depends on the portal
grant from the file dialog, exactly as the capture feature already does.

The metainfo file needs no change: it carries a summary and one description
line, with no feature list.

## Testing

**Existing tests that move with the code**, all of them guards:

| Test | Change |
|---|---|
| `test_packaging::test_manifest_permissions` | the grant swap |
| `test_tile::test_mpv_options_match_spec` | `cache=yes` plus the two new keys |
| `test_settings::test_default_capture_folder_matches_spec` | `~/Videos/Striem` |
| `test_capture` | the `extension` parameter |

**New unit tests**, Qt-free like the rest of `capture.py`: the `extension`
parameter, and `recording_filename` covering the `-rec` marker and the
`-rec2`, `-rec3` part sequence, so the reconnect rule is testable rather than
buried in Qt.

**Not unit-tested**, following this repo's precedent that Qt widgets are never
instantiated in tests: the Qt and mpv wiring. Verified instead by extending
`scripts/snapshot.py` with `clip`, `record` and `stop` steps driving the real
app against `scripts/fakecams.sh`, plus two manual cases: killing a stream
mid-recording to exercise the part-file path, and quitting while recording to
confirm containers finalise.

**Not testable on macOS:** the Flatpak sandbox. This changes the grant rather
than adding one, so it needs a build on Bazzite to confirm. The subpath syntax
`xdg-videos/Striem:create` is also unverified on a real build.

## Known limitations

- A disk filling mid-recording may not be noticed promptly: mpv stops writing
  and the app has no reliable signal. Recorded in the same spirit as the
  original spec's stalled-stream limitation.
- Retained buffer duration varies with bitrate, because mpv's back buffer is
  sized in bytes. The app reports what it actually wrote rather than claiming N.

## First implementation task

Verify the `demuxer-cache-state` field names (`cache-begin`, `reader-pts`)
before any code depends on them. The probe printed only `total-bytes` and
`fw-bytes`, so the fields used to compute the available back-window follow
mpv's documentation but are not yet confirmed here.

## Out of scope

Re-encoding, clip trimming or preview, scheduled or motion-triggered recording,
audio-only capture, uploading clips anywhere, and a media browser inside the
app. PTZ, motion detection and authentication remain out of scope from the
original spec.
