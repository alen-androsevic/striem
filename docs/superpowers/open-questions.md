# Open questions and autonomous decisions

A running log for work done while Alen is away. Two parts: things that need a
human answer, and calls I made on his behalf so they can be reversed cheaply.

Last updated: 2026-09-12, during the clips and recording work.

---

## Questions that need you

### 1. The Flatpak build has never been run (blocks release, not development)

The capture feature and the clips feature both change `finish-args`, and neither
change has been built. `build.sh` only runs on Linux, so nothing in this work
has been exercised inside an actual sandbox.

- Capture shipped `--filesystem=xdg-pictures:create`.
- Clips replaces it with `--filesystem=xdg-videos/Striem:create`.

The syntax is confirmed against Flatpak's documentation (`xdg-*` tokens accept a
trailing subpath, and `:create` covers the app creating the directory itself),
but documentation is not a build. **Please run `./build.sh` on Bazzite and try
saving a still and a clip.** If writes fail there, the fallback is widening to
`~/Videos/Striem:create` spelled relative to home, or `home:create` as a last
resort — I would rather you chose than have me quietly broaden the sandbox.

### 2. What bitrate are your actual cameras?

The back buffer is 32 MiB per camera, which decides how much history a clip can
reach back through. Measured against the 640x360 test streams that is ~80 KB/s,
so 32 MiB is many minutes. Against real cameras:

| Camera bitrate | ~Seconds held in 32 MiB |
|---|---|
| 2 Mbps | ~130 s |
| 4 Mbps | ~65 s |
| 8 Mbps | ~32 s |
| 16 Mbps | ~16 s |

So 32 MiB comfortably covers a 30 s clip up to about 8 Mbps, and silently gives
you a shorter clip above that. The app reports the duration it actually wrote,
so it will never lie to you — but if your cameras are high-bitrate, say the word
and I will raise the buffer.

### 3. Branch strategy

Nothing is pushed. The branches are stacked because the clips work modifies the
capture work's code:

```
next
 └── feat/camera-capture    snapshot feature
      └── feat/camera-clips  clips and recording
```

Options: two stacked PRs in order, or squash both into one. I defaulted to
keeping them separate, since they are separately reviewable features. Tell me if
you want them combined, or want the capture PR opened now.

### 4. Are `C` and `R` the right keys?

Both are unbound in the app today, and the existing keys (`1`-`9`, `0`, `Esc`,
`M`, `S`, `F11`, plus the Konami arrows/`B`/`A`) are untouched. But you are the
one with the muscle memory. `C` = clip, `R` = record.

---

## Decisions I made on your behalf

Each one is cheap to reverse; the "to change" line says how.

### Treated "go ahead and work" as approval of the spec

The brainstorming process had a review gate after the spec was committed. I read
your instruction as clearing it. *To change:* tell me what you want different in
the spec and I will revise before the affected tasks run.

### Inline execution rather than subagent-driven

The writing-plans skill offers a fresh subagent per task. I chose inline: the 12
tasks are sequential and repeatedly touch the same files — `window.py` appears in
five of them — so parallel agents in a 1500-LOC repo would collide more than they
would help. I did use one agent for the Flatpak research, which was genuinely
independent. *To change:* say so and I will dispatch per-task subagents.

### Corrected the spec in a follow-up commit rather than amending

The committed spec claimed `demuxer-cache-state` exposes `cache-begin`. It does
not — verified against mpv 0.41. I corrected it in a new commit rather than
rewriting the original, so the mistake and its correction both stay visible.
*To change:* squash them when the branch merges.

### Clip length prompt is bounded 1-300 seconds

An arbitrary range wide enough to be useful and narrow enough that nobody sets
it to something the buffer cannot honour. *To change:* one line in
`_choose_clip_length`.

### The REC indicator is steady, not blinking

A blink needs a timer per tile for no information gain, and this app already runs
a reconnect timer per tile. *To change:* one timer in `tile.py`.

### Recording files are marked `-rec`, later parts `-rec2`, `-rec3`

So a 30-second clip and a twenty-minute recording are distinguishable in a folder
listing. Parts exist because mpv overwrites its `stream-record` target, so
resuming after a reconnect into the same name would destroy what was already
captured. *To change:* `recording_filename` in `striem/capture.py`.

---

## Verified along the way

Findings that cost real probing, recorded so nobody re-derives them:

- `profile=low-latency` never set `cache=no`. That was this app's own separate
  choice, so a back buffer does not contradict the profile.
- `demuxer-lavf-probe-info=nostreams`, from that profile, is the single reason
  container writing produced 0-byte files. Overriding just that one option fixes
  both `dump-cache` and `stream-record`, and costs no measurable startup latency.
- `dump-cache` with `end="no"` on a live stream **never returns**. Always bound
  the end. Bounded, it returns in ~0 s.
- `demuxer-cache-state` has no `cache-begin`. Use `seekable-ranges`.
- `screenshot_raw` requires Pillow; `screenshot_to_file` does not.
