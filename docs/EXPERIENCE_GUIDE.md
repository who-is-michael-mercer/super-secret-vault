# Try the completed Relay experience

The current checkout already has a built viewer, an editable Relay installation,
and a separate demo under `.local/demo/`. The demo password is public: **13001300**.
Use it only for disposable data. Your ordinary Relay home and existing carriers
are not used by the demo script.

## Start here

From the project directory:

```sh
.venv/bin/python scripts/experience_demo.py
```

This opens `.local/demo/evening.png` in the pinned, patched Swayimg. It is an
ordinary night-landscape PNG containing a real encrypted vault, initially with
`welcome.txt`. The image itself contains no visible Relay label.

1. Press **1** for 100% image scale. Leave the moon near the window center.
   Default enrollment accepts scale 0.9–1.1 and the central 10% image rectangle
   within 12% of the window center; at least 90% of that rectangle must be visible.
2. Tap and release **Home, F7, End, PrtSc, PgUp, Caps Lock, Esc, Home**.
   Do not press Enter. A correct pose and sequence open a new Foot terminal.
   The image window stays silent on every failed/partial attempt.
3. At the image inspector, tap **Home, F8, PgUp, End**. No Enter.
4. Watch the vault assemble. When it has stopped drawing, tap
   **Left, Right, F7, Home**. No Enter.
5. After the vault dissolves, type these commands, with Enter after each:

   ```text
   peel
   follow 3
   open
   ```

6. At the separate real authentication screen, type **13001300**, then Enter.
   The numeric demo password avoids Caps Lock ambiguity. Your real password is
   always case-sensitive; Caps Lock in the image sequence retains its normal toggle.
7. In the authenticated vault, try:

   ```text
   list
   info welcome.txt
   help
   ```

The complete path is:

```text
PNG -> visual door -> inspector -> construction -> silent vault -> dissolve
    -> fictional route -> password authentication -> encrypted vault session
```

## Exercise real file operations

For the default demo location, from the unlocked prompt:

```text
store "/home/michael/Projects/local-repo/SSV_v3/.local/demo/welcome.txt" test-copy
list
retrieve test-copy "/home/michael/Projects/local-repo/SSV_v3/.local/demo/retrieved.txt"
lock
```

Retrieval refuses to overwrite an existing destination; choose a new name on a
second attempt. `lock` returns to the inspector. Repeat the two terminal sequences
and route to reopen. The image sequence is not required while that terminal is open.

To test reopening through the image instead, use `exit` in the vault, return to
Swayimg and press **o** to reload after a store/rename/remove changed the carrier.
Then enter the image sequence again. This reload is deliberate: the old displayed
image must not qualify a newly replaced file at the same path.

`exit` closes the launched session/Foot window normally. **q** closes Swayimg.
The viewer-scoped parent exits after its viewer and any launched terminal finish;
there is no service to stop and no login startup to disable.

## Adjust the presentation

These commands affect only the demo's local policy:

```sh
RELAY_HOME="$PWD/.local/demo/state" .venv/bin/relay configure --animation-speed fast
RELAY_HOME="$PWD/.local/demo/state" .venv/bin/relay configure --effects off
RELAY_HOME="$PWD/.local/demo/state" .venv/bin/relay configure --presentation text
```

Restore the default presentation:

```sh
RELAY_HOME="$PWD/.local/demo/state" .venv/bin/relay configure --effects on --animation-speed normal --presentation ascii
```

Normal construction takes 3.6s and dissolution .95s. Fast takes 1.4s + .5s; slow
5.4s + 1.6s. Effects-off and text presentation are immediate, but still require
both hidden sequences. Very small terminals use a compact vault. Large canvases
are bounded at 240 columns by 80 rows; resize safely redraws the current stage.

Direct terminal and maintenance entrypoints are useful for comparing the ritual:

```sh
.venv/bin/python scripts/experience_demo.py --terminal
.venv/bin/python scripts/experience_demo.py --maintenance
```

Maintenance skips concealment and still requires the real password. To create a
second independent demo, use `--directory /absolute/path/to/a/new-demo`; existing
demo data is never reset or overwritten automatically.

## Use your own carrier / rebuild elsewhere

Current support is Arch Linux, Hyprland, native Wayland and the qualified Foot
profile. Python 3.12+ is required. Source compilation needs a C++20 compiler,
pkg-config, Wayland client/protocols/scanner, xkbcommon, Fontconfig, FreeType, Lua
and libpng. Those dependencies are already present on the qualified machine.
The commands below do not install system packages or require root.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]' meson==1.12.0 ninja==1.13.2
PATH="$PWD/.venv/bin:$PATH" python integrations/swayimg/build.py .local/swayimg
relay init /absolute/path/to/quiet.png --image /absolute/path/to/original.png
relay door enroll /absolute/path/to/quiet.png
relay view --viewer "$PWD/.local/swayimg/build/swayimg"
```

Skip the build command when that destination is already built. It pins Swayimg
`7e7590a19ab5e93f1272ecb810e47f4d8a163549` (`5.6-9-g7e7590a`, with the included
Relay patch). Stock Swayimg is insufficient. The system viewer and file
associations are unchanged; use `relay view` to open the enrolled carrier with
this integration. Ordinary `relay open IMAGE` starts at the inspector.

Enrollment overrides, using image coordinates and fractions of window size:

```sh
relay door enroll /absolute/path/to/quiet.png --region 350 250 100 100 --zoom 0.9 1.1 --tolerance 0.12 0.12
relay configure --inspector-sequence KEY_HOME KEY_F8 KEY_PGUP KEY_END
relay configure --vault-sequence KEY_LEFT KEY_RIGHT KEY_F7 KEY_HOME
relay configure --sequence-timeout 5 --idle 300
relay door disable
```

Local policy lives in `RELAY_HOME/preferences.json`, normally
`~/.relayvault/preferences.json`, mode 0600. The image sequence is configurable in
`image_door.sequence` using supported `KEY_` names. `KEY_PRINT` means physical
PrtSc / Linux `KEY_SYSRQ` 99, not Linux AC Print 210. No password or factor material
is placed in these preferences. Version 1 preferences migrate without enabling
the image door; the old `wake` is retained for `open --legacy-wake`.

## If nothing happens

Silent failure is intentional. Verify the configured image, 100% scale and center
position; release all keys, wait five seconds and retry. Pan with **h j k l**, zoom
with **z/x** or **=/−**, reset with **r**, reload with **o**. Rotation or mirroring
requires reload before eligibility returns. Moving focus or changing the view
resets the partial image sequence. Holding a key across focus also blocks matching
until released. Bare PrtSc must reach the viewer: the qualified owner's screenshot
binding is already **Shift+PrtSc**. The integration never adds a global key listener.

Rename the carrier or replace its ordinary image bytes only with deliberate
re-enrollment. Atomic vault updates preserve the ordinary image binding but require
viewer reload. Symlink/hardlink aliases are rejected. Close and restart the viewer
after editing its sequence/geometry policy. `door disable` takes effect for new
launch requests without requiring a restart.

The decoder limits this profile to static PNG, at most 16,384 pixels per side and
64 Mi pixels total, 128 MiB of ordinary PNG structure and 1,152 MiB total carrier.
These are viewer/inspection limits, not changes to the cryptographic format.
Very large carriers require streaming CRC checks during handoff and inspection.
The inspector reports PNG structure/CRCs; it does not claim cryptographic integrity.

## What to evaluate

Most useful feedback: pose tolerance; the three sequences; inspector credibility;
vault proportions at your usual terminal size; construction/dissolution pacing;
the amount of silence; route wording and complexity; the change into real
authentication; and whether repeated use remains comfortable.

Physical image keys were qualified in Stage 1B. Final automated tests also exercise
native Swayimg and real Foot with an explicit viewer-local synthetic event driver
and private PTY input. They do not replace your subjective acceptance or constitute
new physical-key evidence. X11, XWayland, other viewers and other terminal profiles
remain unqualified. Classic terminal input cannot prove a key was physically typed
or distinguish every repeat; bracketed paste is rejected for hidden sequences.

Concealment can be bypassed by the owner or a same-user process. Process names,
arguments, preferences, file sizes and filesystem activity remain observable.
Password authentication and encryption provide protection. YubiKey is future work.
EOF, Ctrl+C, hangup and termination restore terminal state where the terminal still
exists, close authenticated sessions and stop their timers. No logout, reboot,
shutdown or terminal-destruction action is enabled for the demo.

To re-enable a deliberately disabled demo door:

```sh
RELAY_HOME="$PWD/.local/demo/state" .venv/bin/relay door enroll "$PWD/.local/demo/evening.png"
```
