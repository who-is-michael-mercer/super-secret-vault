# Isolated imv feasibility probe — experience Stage 1 only

This is development instrumentation, **not the Relay doorway**. It displays an
`ELIGIBLE` / `INELIGIBLE` overlay and reports viewer state. A successful fixed test
sequence increments a counter; it cannot launch Relay or a terminal. No production
settings/input/animation/authentication changes are included.

The pin is in [upstream.json](upstream.json): SourceHut imv **v5.0.1**, commit
`bdec0e527be289e08c3a70c8719a85994d26bd4d`. The planning document's GitHub revision
was an archived 2021 tree, not the current upstream. This probe deliberately uses
the release corresponding to the installed system viewer. The system package is
not changed. Upstream's MIT license is reproduced in [UPSTREAM_LICENSE](UPSTREAM_LICENSE).

## Build without installation

Build tools can live in a disposable virtual environment. Existing system headers
are used; this does not install system libraries or add Relay runtime dependencies.

```sh
python -m venv /tmp/relay-imv-tools
/tmp/relay-imv-tools/bin/pip install meson==1.12.0 ninja==1.13.2
PATH=/tmp/relay-imv-tools/bin:$PATH python integrations/imv/build.py /tmp/relay-imv-dev
python integrations/imv/check.py /tmp/relay-imv-dev
```

The checkout destination must be new. The build selects **native Wayland + libpng
only**, with C11 for the focus flag shared with upstream's repeat callback. It
does not run `meson install`, change file associations or write desktop config.
Other decoders have no qualified file-origin stamp and are outside this probe.

Build prerequisites: C compiler, pkg-config, Wayland client/cursor/EGL/protocol
headers and scanner, GL, xkbcommon, pangocairo, ICU and inih, plus libpng. Missing
prerequisites fail the build rather than triggering root/package-manager commands.

## Explicit physical-key session

```sh
python integrations/imv/run_probe.py /tmp/relay-imv-dev/build/imv
```

This creates a private temporary directory with a disposable 800×600 grid PNG and
an isolated imv config. It prints the viewer PID and the directory containing
`latest.json`. Focus that viewer and physically enter:

```text
Home F7 End Pause PgUp CapsLock Esc Home
```

Then press Insert separately. Hold Home to check repeat, release it, and switch to
another application and back. The eight test keys have their normal viewer actions
suppressed in this development build. Caps Lock still changes the desktop lock
state/LED; the probe never synthesizes a compensating key.

Development controls: `z`/`x` zoom, `h/j/k/l` pan, `r` reset, `f` fullscreen, `q`
quit the test viewer. With a partial sequence, exercise those view changes, resize
the window and change focus; prefix must reset. Keep each sequence gap below five
seconds. No key sent by `wtype`, IPC, a terminal paste or a test harness qualifies
as evidence of physical keyboard availability. Do not infer a missing key from
zero counts when nobody has tested it.

`latest.json` is overwritten, not appended. It retains the current pose, prefix
length, match/reset counts, and aggregate `[release, initial_press, repeat]` counts
for HOME, F7, END, PAUSE, PGUP, CAPSLOCK, ESC and INSERT. No arbitrary text or raw
keyboard history is stored. No event records leave the viewer over a socket. The
runner reads its child's stdout; the viewer's built-in IPC is used only by the
separate explicit geometry test. `viewer-errors.txt` receives ordinary viewer
errors for these disposable images, never a keyboard trace.

Until physical Pause testing succeeds or explicitly demonstrates its absence,
there is no basis for recommending Insert as a fallback. The fixed probe sequence
is not migrated into Relay preferences; configurable sequences are Stage 2+ work.

## Actual Wayland window tests, without key synthesis

```sh
python integrations/imv/wayland_check.py /tmp/relay-imv-dev --report /tmp/relay-imv-check.json
```

This briefly opens disposable viewers on the selected Wayland display. It sends
only fixed view/navigation commands to the PID-specific imv IPC of its own child.
A second viewer verifies real focus leave/reenter. It does not query compositor
windows or inject keys into the desktop. It terminates only the viewer children it
created; it never closes a terminal, logs out, reboots or shuts down the machine.
The script checks geometry, rotation/mirror rejection, resizing, image changes,
replacement while preserving mtime, stale-display rejection and explicit reload.

The C checks test the exact predicate and pose-invalidation function used by the
viewer, including a seeded partial prefix for each invalidation case. They also
exercise the real libpng/source/image code with stable reads, atomic replacement
and mutation after headers but before pixel decoding. These tests supplement,
and do not substitute for, real keyboard events.

## Observation boundary

* `wl_keyboard.enter/leave` establishes this surface's focus. Key codes come from
  this viewer's Wayland events. Held keys on entry are not counted as fresh presses.
  Initial presses, releases and generated repeats have distinct event states.
* The libpng backend stamps the actual descriptor **before reading headers** and
  checks the same descriptor after decoding. An immutable path/stat stamp travels
  with the decoded image. A later `stat(path)` never replaces that stamp.
* The current selected path, the displayed image's path and the configured absolute
  path must match. The current file must match the decoded device/inode/size/mtime/
  ctime, be owned/regular, and have no hard-link or symlink aliases. This development
  profile uses absolute canonical paths; relative-path convenience is unqualified.
* Viewport offset, scale, image dimensions, rotation and mirror come from imv's
  rendering state. Window/framebuffer dimensions come from its Wayland resize
  events and window. Eligibility is blocked during pending drawing or inconsistent
  resize dimensions. The boundary is the frame submitted by the viewer; it is not
  a claim of knowing the exact physical display scanout time.
* The target rectangle's mapped center must be within the configured x/y fractions
  of window center, at least 90% visible, and within the configured zoom interval.
  Framebuffer pixels are used throughout. Rotated/mirrored images are ineligible.
* Prefix resets on pose/focus/generation/file changes, timeout and unknown presses.
  The development probe is conservative: other non-key viewer events can also
  invalidate a partial prefix. That is not final production interaction policy.

The private environment variables are development controls, not a production
configuration schema: `RELAY_IMV_PROBE` is the absolute test path;
`RELAY_IMV_REGION` is `x y width height zoom_min zoom_max tolerance_x tolerance_y`.
The runner uses `350 250 100 100 0.1 20 0.12 0.12`. The geometry test uses a narrow
zoom interval to exercise rejection. Bad values never become eligible.

## Limits and removal

The observer sees its own window and one configured path. No `/dev/input`, global
shortcuts, screen scraping, desktop polling, network service, login startup or
persistent Relay process is used. The probe ends with its viewer. The test runner
and build tools are explicit development commands.

Stock imv v5.0.1 reload detection uses second-resolution mtime and can miss
same-timestamp replacements. The descriptor stamp detects the stale display and
stays ineligible. Navigate away/back or reopen to decode the replacement. This
probe does not broaden the upstream reload implementation.

Path/stat checks address ordinary local races, not a malicious owner/root process.
They are concealment checks, not authentication. No cryptographic core change is
needed. Multi-seat changes, keymap replacement, fractional scaling and repeat during
focus/teardown still require qualification; no X11/XWayland support is claimed.

Quit the test viewer or stop its runner, then remove the explicitly created temporary
build/session directories when no longer needed. No service needs disabling, and
the system imv remains available. See [recorded evidence](../../docs/verification/EXPERIENCE.md).
