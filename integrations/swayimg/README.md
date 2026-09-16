# Swayimg Stage 1B qualification

An isolated development probe. No production Relay changes, launcher, daemon,
authentication changes or Stage 2 work. The viewer shows only `ELIGIBLE` after a
complete qualifying sequence; all negative states have no overlay. Diagnostics
are explicit development files, not a concealed production feature.

## Pin and build

Upstream: [Swayimg](https://github.com/artemsen/swayimg), commit
`7e7590a19ab5e93f1272ecb810e47f4d8a163549` (`v5.6-9-g7e7590a`). The configuration
API was inspected at this exact revision, including `CONFIG.md` and the Lua,
Wayland, viewer, application and image-loader source. Pin/build details are in
[upstream.json](upstream.json); upstream MIT license is in `UPSTREAM_LICENSE`.

```sh
python -m venv /tmp/relay-swayimg-tools
/tmp/relay-swayimg-tools/bin/pip install meson==1.12.0 ninja==1.13.2
PATH=/tmp/relay-swayimg-tools/bin:$PATH python integrations/swayimg/build.py /tmp/relay-swayimg-dev
python integrations/swayimg/check.py /tmp/relay-swayimg-dev
```

Requires system C++20 compiler, pkg-config, Lua headers, xkbcommon, fontconfig,
FreeType, Wayland client/protocols/scanner and libpng. Nothing invokes an installer,
root, package manager or desktop settings. `auto_features=disabled` excludes
Swayimg's compositor integration and DRM backend; only native Wayland is qualified.
Built-in decoders remain part of upstream, but these tests use disposable PNGs.

## Why stock Lua was insufficient

Stock APIs provide `viewer.get_image()`, `viewer.scale`, `viewer.get_position()`,
`get_window_size()`, `on_redrawn()`, `on_window_resize()` and
`viewer.on_image_change()`. Their coordinates use the rendering buffer, including
the compositor scale factor. Region matching uses one coordinate system.

However, `viewer.on_key()` has no event arguments; initial presses and synthesized
repeats invoke the same callback. Release events are consumed in the Wayland
backend. `wl_keyboard.enter` is an empty callback; leave only stops repeat. There
is no stock Lua focus callback. `get_image()` returns an entry's path/mtime/size,
not provenance for the cached decoded pixels. The stock loader stats a path before
opening and mmaping it, then closes the descriptor before decode.

The opt-in patch adds a queued `on_relay_event(kind, code)` callback, monotonic
`relay_time()`, and decoded-image provenance fields to `get_image()`. Lua is never
called on the Wayland thread. The queue preserves input/focus ordering; upstream
keeps redraw events last. The raw codes are Linux-style codes supplied by this
viewer's **Wayland protocol events**, with no evdev device access.

The source patch was estimated before implementation at 180–220 added lines. See
the verification record for the final measured size and files. A one-line upstream
status-clear redraw fix prevents stale `ELIGIBLE` pixels after invalidation. Most experience
logic remains Lua, using existing supported hooks. This patch is not an upstream
API proposal or a commitment to maintain an expanded fork.

## Physical session

```sh
python integrations/swayimg/run_probe.py /tmp/relay-swayimg-dev/build/swayimg
```

The runner prints its own viewer PID and a private temporary directory containing
`latest.json`. Focus the grid viewer. Release each key and keep gaps below five
seconds:

```text
Home F7 End PrtSc PgUp CapsLock Esc Home
```

PrtSc uses viewer-local Linux `KEY_SYSRQ` code 99, not `KEY_PRINT` code 210.
The owner explicitly selected it after confirming that the keyboard has no Pause
key. Test Insert separately; neither Insert nor Pause substitutes for PrtSc.
On this machine screenshots were moved from bare PrtSc to Shift + PrtSc in the
owner's Hyprland overrides. This adds no Relay compositor binding or input listener.
Verify the screenshot picker with Shift + PrtSc, then cancel without capturing.
Hold Home to observe repeat, release it, and change focus. For held-before-focus,
hold Home outside the viewer, focus the viewer with the mouse while holding Home,
then release it. No synthetic-input tool is used; those events would not prove
physical availability. Caps Lock still changes the keyboard lock/LED state.

Development controls: `r` restores centered 100% scale, `z/x` zoom, `h/j/k/l` pan,
`n/b` switch images, `o` reloads, `f` toggles full screen, `]` rotates, `m` mirrors,
and `q` exits **only this viewer**. Esc is reserved for sequence testing. Restoring
geometry after an invalidation never restores a previous partial sequence.

`latest.json` is overwritten atomically. It contains the current pose, current
eligibility, prefix length, completion/reset totals, focus/keymap/held totals,
blocked-input totals and press/release/repeat aggregates for only the eight named
keys. It contains no arbitrary text, ordered key history or passwords. Unknown
keys reset the matcher and are not retained. A held-key set exists only in memory
until release/focus loss. No key event is exported over IPC.
`last-success.json` is also overwritten, only when a full sequence satisfies the
actual predicate. It retains the latest successful pose and aggregate counters,
so expiry of the five-second status does not erase qualification evidence. It
contains no additional keyboard history.

## Predicate and reset boundary

The configured absolute image path must equal both the selected entry path and
the immutable decoder-origin path. The current file must match the decoded
device/inode/size/nanosecond mtime/ctime stamp. The target rectangle is mapped into
window coordinates using the current position and scale. Its center must fall
within 12% of each window dimension around the center, at least 90% of its area
must be visible, and scale must be within 0.9–1.1. The fixture region is the central
100×100 pixels of the 800×600 image. Config resides in the disposable directory;
it is not Relay's production settings schema.

Eligibility requires a matching completed redraw snapshot, focus, valid file
identity, qualifying geometry and the full sequence. Wrong keys, focus/keymap
changes, input timeout, image/pose/resize/file changes reset the prefix. Viewer
events conservatively invalidate prefixes even when they do not change geometry;
unchanged pointer movement must not permanently inhibit the next fresh sequence.
Auto-repeat does not advance. Duplicate presses and overlapping held keys fail
closed. Keys listed on focus entry must be released before a sequence can begin.

The patch snapshots at most **16 MiB** of a local regular owner-owned file into a
private buffer, checks the same descriptor before/after reading, then passes that
buffer through the real decoder. No mmap is used in this opt-in path, so concurrent
truncation cannot invalidate the input mapping. The provenance travels with the
decoded image through Swayimg's history cache. Transforming decoded pixels makes
the original-coordinate predicate ineligible until reload; rotated/mirrored
eligibility is deliberately unqualified. Files larger than the development limit,
symlinks, paths containing directory symlinks and hardlink aliases are rejected.
This is a test profile limit, not a change to Relay's carrier size or formats.

No file-monitor integration is enabled: replacement must remain visibly stale
until an explicit reload. A 100 ms Lua timer checks only this viewer's state and
the configured displayed-file stamp for timeout/removal/replacement. Every relevant
key event also checks identity immediately. This is not desktop polling or a
persistent process. Same-user/root tampering is outside these concealment checks.

## Automated checks

```sh
python integrations/swayimg/check.py /tmp/relay-swayimg-dev
python integrations/swayimg/wayland_check.py /tmp/relay-swayimg-dev/build/swayimg --report /tmp/swayimg-wayland.json
```

The first command runs deterministic Lua matching/geometry checks and links the
real built upstream objects into a headless PNG origin test. The second opens
temporary Wayland viewers. A private fixed-command Lua `on_signal` handler exercises
only geometry/navigation/reload through supported APIs. It never sends key events,
calls compositor IPC, injects a sequence or launches a terminal. Only children it
created are terminated. An opt-in test seam seeds only a partial prefix to verify
actual view/file/focus invalidation; it cannot seed a completed match and is not
enabled in the physical runner. Its geometry successes cannot substitute for the separate
physical sequence test.

Quit the probe with `q` or stop its runner when finished. No service needs disabling.
Keep or remove the explicitly created temporary checkout/session directories as
desired. System viewers, associations and the production vault remain unchanged.

Actual results and limitations: [Stage 1B verification](../../docs/verification/SWAYIMG_STAGE1B.md).

## Production experience integration (Stages 2–8)

Swayimg is now the official native Wayland/Hyprland target. `build.py` defaults to
`relay-door.patch`; `--probe` preserves the historical Stage 1B build. Both apply
to the exact revision in `upstream.json`. No system package or associations change.

From the project directory:

```sh
.venv/bin/python -m pip install meson==1.12.0 ninja==1.13.2
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python integrations/swayimg/build.py .local/swayimg
.venv/bin/relay door enroll /absolute/path/to/carrier.png
.venv/bin/relay view --viewer "$PWD/.local/swayimg/build/swayimg"
```

Build destination must be new. The already-built `.local/swayimg` can be reused.
Required system build libraries: C/C++20 compiler, pkg-config, Wayland client and
protocols/scanner, xkbcommon, fontconfig, FreeType, Lua and libpng. Foot must exist
for the fixed terminal profile. No root installation is performed by these tools.

Enrollment defaults to the central 10% rectangle, scale 0.9–1.1, center tolerance
12% of window width/height and at least 90% of the target visible. Override with
`door enroll IMAGE --region X Y W H --zoom MIN MAX --tolerance X Y`.
Use `1` for 100% scale, `z`/`x` or `=`/`-` for zoom, `h j k l` for pan,
`r` for reset, `o` for reload, `f` for fullscreen and `q` to close the viewer.
Rotation/mirroring deliberately disqualify until reload. The image window displays
no Relay status. Sequence: Home, F7, End, **PrtSc**, PgUp, Caps Lock, Esc, Home.
Tap and release each key. Bare PrtSc must reach the viewer; on the qualified owner
machine screenshots already use Shift+PrtSc. Caps Lock retains its ordinary toggle
behavior; check its state before typing the password.

`relay door disable` removes enrollment. Close the viewer to stop its scoped
broker. There is no login startup, daemon, desktop observer or global input hook.
An existing launched terminal may keep the broker alive until that terminal exits.

The viewer sends only a completed-match source stamp through an inherited local
socket. The broker rechecks the ordinary-PNG digest and file stamp, takes a per-path
advisory lock in the owner runtime directory (across local profiles) and launches Foot with a fixed argv (no shell). Relay rechecks before
opening. A stamp is a race guard for concealment, not an authentication token.
A same-owner process can bypass the ritual using ordinary maintenance access.

The production reader skips `rvLt` chunk bytes on the original file descriptor
and decodes a bounded private copy of ordinary PNG chunks: at most 128 MiB image
structure and 1,152 MiB total file, consistent with the existing format bounds.
The Python handoff scanner validates all CRCs in bounded 64 KiB pieces. It does
not decode capsule metadata. Atomic vault writes preserve enrollment but invalidate
old displayed pixels: explicitly reload (`o`) before reopening. Rename requires
re-enrollment; symlink/hardlink aliases and changed ordinary image bytes fail closed.

Checks (never inject desktop keys):

```sh
.venv/bin/python integrations/swayimg/check.py .local/swayimg
RELAY_SWAYIMG_DOOR=1 .venv/bin/python integrations/swayimg/wayland_check.py .local/swayimg/build/swayimg --report .local/wayland.json
.venv/bin/python integrations/swayimg/handoff_check.py .local/swayimg/build/swayimg
```

The check wrapper's explicit handoff is test-only and does not establish a new
physical-key result. X11 and XWayland remain unqualified. The patched binary is an
explicitly selected viewer; opening a PNG in an unrelated/system viewer cannot wake
Relay. Process names, argv, local preferences, file size and filesystem activity
remain observable. None of this concealment replaces password authentication.

Final production guardrails: static PNG only, at most 16,384 pixels per side and
64 Mi pixels decoded. PNG metadata allocation/cache limits are set before decode.
The final patch is 195 added / 3 removed lines in 12 files, at the same pin.
See [the owner walkthrough](../../docs/EXPERIENCE_GUIDE.md) and
[implementation verification](../../docs/verification/EXPERIENCE_IMPLEMENTATION.md).
