# Relay: the image doorway and terminal experience

Status: **implemented through Stage 8 and engineering-qualified (2026-09-14)**.
The complete experience is ready for owner testing and subjective feedback.
Swayimg is the official viewer for Arch Linux / Hyprland / native Wayland.
The owner approved the full remaining experience after Stage 1B passed.
Current image sequence: `KEY_HOME KEY_F7 KEY_END KEY_PRINT KEY_PGUP
KEY_CAPSLOCK KEY_ESC KEY_HOME`. Relay `KEY_PRINT` names physical PrtSc
(Linux `KEY_SYSRQ`, 99), never Linux AC Print (210).
Terminal sequences: `KEY_HOME KEY_F8 KEY_PGUP KEY_END` and
`KEY_LEFT KEY_RIGHT KEY_F7 KEY_HOME`. These are now approved defaults.
See [implementation tracking](verification/EXPERIENCE_IMPLEMENTATION.md).
The original research/authorization notes below are preserved as history;
the current authorization supersedes their earlier stop conditions.

Original viewer approval: imv with a small Relay-specific integration patch;
the owner subsequently authorized Swayimg qualification under Stage 1B. Current
owner-selected image sequence: `KEY_HOME KEY_F7 KEY_END KEY_SYSRQ KEY_PGUP
KEY_CAPSLOCK KEY_ESC KEY_HOME`, with `KEY_SYSRQ` labeled **PrtSc**. This supersedes
the original Pause choice because the owner has no Pause key. Insert remains a
separate diagnostic key. The owner approved moving local screenshots from bare
PrtSc to Shift + PrtSc; no global Relay binding is added. Earlier Pause examples
below are historical research, not the currently selected sequence.
No global input capture, input-device monitoring, desktop polling/scraping or
persistent Relay service. Keep the crypto/storage core intact. Password is real
authentication; hardware authentication is deferred. Stop after the Stage 1 gate.
The two later terminal sequences and presentation defaults remain design proposals.

Stage 1B outcome: **Swayimg passes the native Wayland qualification with PrtSc and
is recommended for the visual door.** Its final development patch is 125 added /
3 removed lines across 11 upstream files. See
[Stage 1B evidence](verification/SWAYIMG_STAGE1B.md) for the three actual physical
matches, held-key rejection, geometry/identity tests and remaining profile limits.
The imv-specific sections below preserve the original approved design history;
the current qualification result supersedes that viewer recommendation. No Stage 2
or later implementation is authorized by this result.

Stage 1 research correction: the earlier GitHub source pin below is an archived
2021 tree. The isolated probe uses active SourceHut imv v5.0.1 at
`bdec0e527be289e08c3a70c8719a85994d26bd4d`; see the verification record for actual
observations, patch size, limitations and the gate verdict. Earlier source-level
claims must not be mistaken for qualification of the current release.

Prepared 2026-09-13 on `v3/design`, against repository commit
`37fc810f1267dd0e692a94764c8710f39d3c59a8`.

The recommendation is one supported viewer, **imv with a narrowly scoped,
opt-in integration patch**, followed by an honest image inspector, a terminal-native
vault construction, a silent hold, a reverse-construction transition, and a
three-command fictional route to real password authentication. No desktop-wide
keyboard listener, login daemon, or cryptographic format change is proposed.

Stock imv does **not** provide every required hook. Shipping the doorway includes
maintaining and testing that patch; it must not be represented as a configuration-only
feature. Its feasibility is the first implementation gate. If the patch proves too
large, revisit this recommendation before implementing a fallback listener.

`IMPLEMENTATION_PLAN.md` remains authoritative and now references this approved
subsequent experience phase. Its original V3 stages are complete. The optional
viewer patch is authorized for the isolated Stage 1 probe; the later fixed-argv
terminal launcher is not yet authorized. No plugin framework or shell execution
is needed. Keep the prohibition on daemons, network features, and shell commands
in the fictional route. See [current evidence](verification/EXPERIENCE.md).

## 1. Current-state assessment

### Lifecycle and reusable pieces

| Existing code | Current behavior | Proposed treatment |
| --- | --- | --- |
| `main.py` | CLI, cover loop, short waking transition, route dispatch, password prompts, authenticated commands | Extend presentation states; retain CLI maintenance and vault operations |
| `input.py` | One `TTYInput` owner, cbreak/no echo, alternate screen, bracketed paste, bounded decoding, line editing, signals, boundary draining | Preserve ownership and cleanup; extend decoder and matcher capabilities |
| `cover.py` | Relay logo/version, kernel/uptime, basename, suffix-derived media type and actual size | Replace visible content; retain the principle of sanitized, unauthenticated public information |
| `access.py` / `topology.py` | Fixed in-memory resources; `attach 13`, `unlock`; explicit authenticate action | Replace topology and copy without giving the controller I/O capabilities |
| `terminal.py` | Standard-library effects, injected timing, mostly line-based redraw, construction-time width | Add bounded full-screen frame rendering with live width/height; do not use its separate keyboard context |
| `settings.py` | Strict version-1 JSON, exact field validation, atomic private writes | Add explicit local schema migration and bounded experience settings |
| `auth.py` / `main.authenticate` | Identity-scoped local backoff, secret password input, three attempts | Reuse; make real authentication visibly distinct |
| `vault/session.py` | Authenticated session, serialized operations, watchdog, locking and best-effort wiping | Keep its public authentication/session contract |
| `vault/crypto.py`, `capsule.py` | Fixed Argon2id/AES-GCM design; authenticated manifest and records; bounded capsule framing | Preserve unchanged |
| `vault/png.py` | PNG framing/CRC and private segment validation; streaming embedding/reassembly | Preserve carrier semantics and recovery behavior |
| `vault/store.py`, `migration.py` | Stable locks, verified backup/staging, source checks, atomic publication, migration and recovery | Preserve unchanged |

Today, `relay open` itself opens no terminal: it runs in the caller's terminal.
There is no image watcher. The carrier can already be an ordinary valid PNG.
The current sequence is `COVER → WAKING → ROUTE → AUTHENTICATING → UNLOCKED`.
`lock`, inactivity and normal session completion return to cover. Maintenance
bypasses concealment and goes directly to authentication.

`WakeMatcher` already performs suffix/prefix overlap matching and a five-second
inter-key reset. It stores at most a sequence prefix. The decoder recognizes arrows,
ordinary characters and paste, but lacks named Home/End/function keys; a lone Escape
currently expires as unknown input. `TTYInput` already drains queued events, partial
bytes and kernel input at boundaries. Preserve this particularly valuable behavior.

`Terminal` couples many ANSI operations to effects being enabled. The new scenes
must separate basic TTY correctness (clear, position, cursor, restoration) from
optional animation. Effects-off must not bring back echo or remove hidden boundaries.

The current core derives the encryption key directly from the password. It is not
already a hardware-factor key-envelope design. Adding a cosmetic USB check would
provide no protection against direct capsule access. This phase must leave that
fact explicit.

### Evidence and limits of inspection

Reviewed the requested modules, production vault modules, migration entry points,
input/terminal/CLI/parser/settings tests, `tests/conftest.py`, the authoritative plan,
README, format documentation and verification records. The prior release records
1,321 passing tests, an installed-wheel PTY journey, decoder pixel equivalence,
fresh-home portability and interrupted transaction checks. See
[release verification](verification/RELEASE.md) and [measurements](verification/BASELINE.md).

The local machine has imv **5.0.1**, `hyprctl`, and `foot`; the other queried viewers
were not found on PATH. No viewer was installed or launched, no keyboard device was
opened, and no desktop configuration was changed for this plan. Research establishes
source-level feasibility, not a successful end-to-end doorway demonstration.

Planning-time baseline rerun: `.venv/bin/python -m pytest -q` completed with
**1,321 passed in 37.84 seconds**. The new document also passed whitespace checks.
No production code, tests or authoritative specification were changed.

## 2. Recommended image viewer

### Choose imv, with an explicit integration build

imv supports Linux Wayland and X11, exposes the selected path and zoom percentage
to its commands, and accepts commands over a per-process Unix socket. Its documented
surface does not provide a complete pan/focus snapshot. We must not infer that
`imv-msg` is a state-query subscription API. [imv manual](https://raw.githubusercontent.com/eXeC64/imv/master/doc/imv.1.txt)

The source already has viewport getters for offset, scale, rotation and mirroring,
plus separate logical and framebuffer dimensions. These allow geometry to be
measured inside the rendering process instead of estimated from screenshots.
[Viewport interface](https://raw.githubusercontent.com/eXeC64/imv/master/src/viewport.h),
[window interface](https://raw.githubusercontent.com/eXeC64/imv/master/src/window.h)

The important missing plumbing is concrete: the inspected Wayland keyboard
enter/leave callbacks are empty; its generic keyboard event omits press/release/repeat
classification. The X11 backend receives press/release events but needs explicit
focus handling. Extend these paths narrowly, rather than claiming an existing
plugin API. Source inspected at upstream commit
`2144bea537bff9defc81c34517a939bf361fd736`.
[Wayland backend](https://raw.githubusercontent.com/eXeC64/imv/2144bea537bff9defc81c34517a939bf361fd736/src/wl_window.c),
[X11 backend](https://raw.githubusercontent.com/eXeC64/imv/2144bea537bff9defc81c34517a939bf361fd736/src/x11_window.c)

The integration should be a small patch series against one pinned upstream revision,
with an opt-in feature and tests, not a permanently diverging viewer product. Offer
the generic focus/event additions upstream if appropriate in a separately authorized
step. Do not depend on upstream acceptance. Record license/build/distribution
obligations. Do not silently replace the system package or change PNG associations.

The supported feature means “the tested imv integration build,” not arbitrary imv
versions. Native Wayland is the first qualification target; native X11 is required
before claiming X11 doorway support. XWayland is a separate tested matrix entry.

### Strongest alternatives

| Candidate | Strength | Why not initially |
| --- | --- | --- |
| Swayimg | Excellent native Lua access to image, scale, position, window dimensions and key bindings | Strongest alternative, but Wayland-only; inspected API lacks the complete focus-loss, physical key/release/repeat and atomic observation contract needed here |
| Eye of GNOME (EOG) | Existing viewer-plugin precedent, GTK event handling | Plugin support alone does not establish a supported pan/transform API; GTK/internal widget coupling and another dependency stack need qualification |
| Loupe | Ordinary modern GNOME viewer | No complete supported integration contract was established in this research; accessing private view state or accessibility widgets would be a larger commitment |
| Gwenview | Mature normal desktop viewer | Public user controls are not an API for atomic path/zoom/pan/focus checks; widget inspection or source changes offer no demonstrated advantage over imv |
| Stock imv plus compositor bindings | Already installed; some state available | Cannot prove the viewport from documented exports; global bindings also create unrelated-desktop interception and focus races |

Swayimg's documented Lua API is substantially better than a title scrape. It exposes
`viewer.get_image()`, `viewer.scale`, `viewer.get_position()` and window-size/key
callbacks. However, rebinding only sequence keys would allow unrelated keys between
them unless every input is accounted for; it also needs focus reset and reliable
event provenance. Do not solve that by quietly weakening sequence semantics.
[Swayimg configuration API](https://github.com/artemsen/swayimg/blob/7e7590a19ab5e93f1272ecb810e47f4d8a163549/CONFIG.md),
[project scope](https://raw.githubusercontent.com/artemsen/swayimg/master/README.md)

EOG's plugin history is documented, while Loupe is GNOME's newer default viewer.
Neither fact proves the complete required viewport API. These alternatives are
rejected on demonstrated integration fit, not an assertion that integration is
impossible. [EOG plugins](https://wiki.gnome.org/Apps/EyeOfGnome/Plugins),
[GNOME viewer direction](https://blogs.gnome.org/sophieh/2024/09/20/image-viewing-and-editing-in-gnome-47-and-beyond/),
[Gwenview manual](https://docs.kde.org/stable_kf6/en/gwenview/gwenview/gwenview.pdf)

## 3. Visual-door technical design

### Ownership and observation

Keep recognition **inside the selected viewer instance**, before ordinary viewer
key bindings. It reads only that window's input events and existing in-memory
render state. It never opens `/dev/input`, subscribes to other windows, reads the
clipboard, captures the screen, enumerates desktop titles or observes passwords.

The patch contains one bounded matcher and eligibility predicate. Relay's Python
configuration command writes a small private, versioned viewer-rules file using
imv's existing configuration parsing machinery where feasible. Do not add a C JSON
dependency. That file is generated policy, not a second source of truth. Strings
must be literal values; reject unsupported filename encodings/newlines for doorway
enrollment if the chosen format cannot round-trip them safely. Normal maintenance
continues to work for such paths.

Only a complete successful match starts a **one-shot** Python launcher. That helper
revalidates local policy and file identity and executes a fixed terminal argv. There
is no resident Relay daemon and no per-keystroke subprocess or IPC stream. C and
Python matcher tests share declarative conformance cases; no generic cross-language
event framework is justified.

### Required snapshot and checks

Each eligible key event uses one snapshot from the viewer event-loop thread:

| Fact | Authoritative source and rule |
| --- | --- |
| Viewer identity | The opted-in integration code executing in the pinned imv build; never window title/class as evidence |
| Active window | Keyboard focus for that viewer surface/window and seat; reset immediately on focus leave |
| Active image | Successfully displayed load generation, exact enrolled local path, stable file identity; loading, command console, slideshow and gallery-like modes are ineligible |
| Zoom | Actual renderer scale in a specified coordinate system, not the rounded overlay percentage |
| Viewport | Renderer image origin, transform, framebuffer bounds and image dimensions |
| Input | Initial key press, normalized code and modifiers; never repeated press, text/paste command or IPC invocation |
| Freshness | No intervening focus, file-load, geometry, keymap or rules generation invalidation |

Treat rotation/mirroring and automatic orientation other than the enrolled identity
transform as ineligible initially. Do not approximate rotated rectangles or silently
call displayed coordinates original PNG coordinates. The prototype must establish
decoder orientation behavior using PNGs with orientation metadata.

For an untransformed image, use framebuffer coordinates throughout:

* image pixel point `(x, y)` maps to `(ox + s*x, oy + s*y)`;
* visible image rectangle is the inverse-mapped window rectangle intersected with
  `[0, image_width] × [0, image_height]`;
* configured rectangle `R=(x,y,w,h)` must have at least 90% of its area visible;
* its mapped center must lie within `(tx*W, ty*H)` of the configured normalized
  window anchor `(ax*W, ay*H)`;
* scale must lie in the inclusive configured interval.

Initial tuning: anchor `(0.5,0.5)`, tolerance `(0.12,0.12)`, minimum visible area
0.90. These are testable proposals, not values fitted to an unknown image. Choose
the actual region and zoom during owner-directed enrollment. Normalize imv's
logical/framebuffer units once at the integration boundary; use the same transform
as drawing. Verify 1×, 2× and fractional output scaling before release.

Re-evaluate on every key. Invalidate a partial match on pan, zoom, resize, image
change or focus loss, even if the new state later becomes eligible again. A fresh
sequence may start at any eligible pose. Five seconds without a qualifying press
resets the prefix; wrong presses perform ordinary prefix fallback silently.

### File identity and replacement

Enrollment stores the literal absolute owner-controlled carrier path, dimensions
and a digest of the ordinary image chunks (excluding `rvLt`). The latter binds
the visual image and survives normal Relay snapshot updates; it does **not**
authenticate the encrypted payload. No public capsule identity is needed here.

Reject symlink path components, nonregular files and hard-link aliases for doorway
enrollment, in line with writable carrier policy. Do not accept a matching basename,
another copy, a thumbnail cache entry, or a symlink merely resolving to the carrier.
No directory crawling or automatic “find the renamed file.” Rename requires explicit
reenrollment. Preserve ordinary viewer behavior for other files.

Associate each decoded display generation with the file identity observed during
that load: device, inode, size and nanosecond mtime/ctime. A path stat
performed only after decoding is insufficient: it can describe replacement bytes
while the viewer still displays the previous image. Bracket loading with identity
checks and tie them to the source actually decoded; if a backend cannot establish
that, disable the doorway for that backend until fixed. Do not introduce a second
pixel decoder into Relay.

Re-stat during recognition and at launch. Invalidate immediately on mismatch;
require a successfully revalidated reload and a fresh sequence. The Python launcher
checks the enrolled visual digest after a complete match but before opening any
terminal, with before/after file identity checks against the displayed generation.
This keeps SHA-256 in Python's standard library instead of adding a C crypto
dependency. The viewer's initial path/stat check is provisional until this final
binding check succeeds. Stream/hash ordinary chunk bytes and seek past bounded
private payload ranges; do not read or hash a GiB payload per key. The final helper
check may take noticeable time for a large ordinary image and must produce no UI.

Do **not** pin an inode forever: `Store.commit` deliberately replaces the carrier.
After a legitimate commit the viewer must reload and revalidate the image binding,
then the doorway works again. A same-picture replacement capsule can still pass
concealment; password/AEAD verification remains authoritative. A malicious same-user
writer can defeat stat-based observation. Do not claim protection from that attacker
or rollback prevention.

### Key binding side effects and silent failure

While the enrolled image is visually eligible, reserve the configured sequence's
non-character keys before viewer bindings. Consume those keys even on mismatch,
without executing buffered actions later. Other keys retain their normal viewer
behavior and reset/fallback the matcher. Outside eligibility, normal imv behavior
continues. “Nothing happens” means no Relay launch, UI, sound or diagnostic; it
does not promise that ordinary viewer shortcuts or Caps Lock stop working globally.

This avoids Home/PgUp/Escape changing the file or closing the viewer halfway through
the sequence. Do not replay delayed Escape or Delete after a failed attempt. Input
reservations are themselves potentially observable concealment artifacts.

Caps Lock may change the desktop's lock state and LED before the viewer sees it.
Never synthesize another key or rewrite compositor state to undo this. Ignore lock
state for non-character sequence matching, leave it as the user set it, and explain
the side effect in owner documentation. An owner can substitute another key.

### Launch lifecycle

At the final initial press, atomically mark this viewer attempt consumed and capture
the selected path/load identity. Spawn the fixed helper with structured arguments
or an inherited bounded record, never a shell string or a command from the PNG.
No password, sequence history or capsule data is sent. The helper validates its
bounded input and current owner policy, reopens with no-follow checks, and confirms
identity before launch.

Start one new terminal process with a fixed profile, initially `foot` on the local
Wayland system, passing `relay open` plus the fixed selected target and an internal
expected-file-identity precondition. The Relay process rechecks this precondition
before displaying the inspector. It exits quietly if stale. This precondition is
a race guard, **not a secret token or authorization capability**. Direct CLI access
and maintenance intentionally remain possible.

The helper holds an owner-private runtime advisory lock for the target while its
non-daemonizing terminal child runs. Concurrent successful attempts then silently
do nothing; OS lock release handles crashes. Bound repeated failed-launch retries,
reap children, close inherited descriptors, and never capture or persist terminal
output. Missing terminal/display, malformed rules or launch failure is silent.
No generic terminal command string: validate an explicit executable/profile and
fixed argument layout; test filenames containing spaces, quotes and leading `-`.
The X11 qualification stage needs a tested X11 terminal profile; `foot` does not
establish that support.

The final-key snapshot is the trigger point. A focus change after that point cannot
atomically cancel a process spawn across the compositor; recheck immediately before
handoff where possible and document this small launch race. A mid-sequence close or
focus change must always cancel. Whether the newly created terminal receives focus
is compositor policy; do not bypass it with global input grabs or unsolicited rules.

### Wayland, X11 and startup

Wayland delivers keyboard events to the entered surface and supplies a keymap and
key state. Use those events, not a global “active window” poll. Add focus-leave
invalidation and stop treating generated repeat events as new presses.
[Wayland keyboard protocol](https://wayland.freedesktop.org/docs/html/apa.html#protocol-spec-wl_keyboard)

For X11, select focus events, verify input focus belongs to this window, reject
obvious `send_event` synthetic events, and correctly distinguish autorepeat. Validate
XKB mapping instead of universally assuming a numeric offset. X11 permits other
clients to inject events; these checks do not create an authentication boundary.
XWayland has the same limitation among its X clients. Unknown keymap/seat/focus
conditions disable matching, rather than falling back to global observation.

Installation/enabling is an explicit future owner action. The viewer's ordinary
launch reads the opt-in rules; no login startup is required. Disabling the feature
removes/disables those rules and restarting the viewer clears in-memory prefixes.
Uninstalling the optional build restores stock imv. No systemd user service is
recommended. If a later proposal requires one, it needs its own observation contract,
explicit opt-in unit and disable instructions; it must not be quietly introduced
as this plan's fallback.

## 4. Input subsystem redesign

### Names and capabilities

Use a small canonical Linux-style token vocabulary, with separate viewer and TTY
adapters. Do not pretend a terminal byte stream is evdev.

| Owner token | Linux code name | Viewer expectation | Ordinary terminal expectation |
| --- | --- | --- | --- |
| `KEY_HOME`, `KEY_END` | Same | Initial presses | CSI/SS3 variants |
| `KEY_PGUP`, `KEY_PGDN` | `KEY_PAGEUP`, `KEY_PAGEDOWN` | Initial presses | Usually CSI `5~`, `6~` |
| `KEY_INSERT`, `KEY_DELETE` | Same | Initial presses | Usually CSI `2~`, `3~` |
| `KEY_ESC` | Same | Unambiguous event | Lone Escape needs disambiguation timeout |
| `KEY_CAPSLOCK` | Same | Physical event, independent of lock state | Usually no event; reject in baseline TTY sequences |
| `KEY_F1`–`KEY_F12` | Same | Depends on keyboard function-row mode | SS3/CSI variants; emulator shortcuts may intercept |
| `KEY_F13`–`KEY_F24` | Same | Valid codes, often absent on hardware | Extended/capability-tested only |
| `KEY_UP/DOWN/LEFT/RIGHT` | Same | Initial presses | Existing CSI/SS3 support |
| `KEY_PAUSE` | Same | Good unusual candidate if keyboard emits it | Not a portable terminal default |

Recommend **`KEY_PAUSE`** for the undecided key: odd, memorable, and less likely
than Print Screen to invoke a compositor action. The proposed image sequence is:

```text
KEY_HOME KEY_F7 KEY_END KEY_PAUSE KEY_PGUP KEY_CAPSLOCK KEY_ESC KEY_HOME
```

Pause is not present on every keyboard. Offer `KEY_INSERT` as a practical substitution
during explicit setup, never a silent runtime substitution. Avoid Power/Sleep,
SysRq and compositor-reserved combinations. Linux defines these key codes, but
their definition does not imply every keyboard emits them. EV_KEY distinguishes
press (1), release (0) and repeat (2).
[Linux event definitions](https://docs.kernel.org/input/event-codes.html),
[Linux key-code header](https://github.com/torvalds/linux/blob/master/include/uapi/linux/input-event-codes.h)

Bare Fn is not an acceptable default. The kernel defines `KEY_FN`, and some drivers
explicitly process it, but that is device-dependent; firmware may consume a layer
key without reporting it. The Apple HID driver demonstrates device-specific Fn
handling, not universal availability. Setup should show only the resulting named
event in an explicitly opened calibration view; do not run evdev capture in the
background to discover it. [Apple HID driver](https://raw.githubusercontent.com/torvalds/linux/master/drivers/hid/hid-apple.c)

Use viewer-delivered Linux key codes on the qualified backend. XKB provides the
translation/capability checks where necessary. Do not use direct evdev device access:
it expands observation to unrelated applications and can require input-group/device
permissions. Global-shortcut portals bind desktop-wide shortcuts, not this complete
viewer geometry/key stream, and can involve visible setup. They are the wrong tool
for eight ordinary keys. [GlobalShortcuts interface](https://github.com/flatpak/xdg-desktop-portal/blob/main/data/org.freedesktop.portal.GlobalShortcuts.xml)

### Matcher semantics

Keep one matcher per active concealment state. Normalize a bounded event into a
token plus source/capability information, optional modifiers, and press classification.
Keep only matched-prefix length/state and monotonic last-press time. No raw input
history. Preserve overlap: `A A A B` satisfies `A A B`; extra wrong keys cannot be
ignored merely because they were not registered sequence keys.

Use initial presses only in the viewer, requiring a release before the same key
can count again. Ignore repeat and releases without extending the deadline. Clear
held-key state on focus/keymap/seat changes. Do not interpret keys listed as already
held on focus entry as newly pressed. For baseline TTY input, repeat cannot always
be distinguished, so choose defaults without consecutive identical tokens and
document the limitation. Optional enhanced terminal protocols are not required.

Support unmodified keys first. A small explicit modifier-set representation may
permit combinations later; reserve Ctrl+C/Ctrl+D and suspension controls for cleanup,
and do not support bare modifiers in portable TTY sequences. No remapping framework.

Expand the existing decoder with common CSI/SS3 Home/End/Insert/Delete/PgUp/PgDn and
F1–F12 encodings. Decode only complete, bounded recognized forms. Lone Escape emits
`KEY_ESC` after the existing approximately 80 ms ambiguity window; incomplete CSI
expires as unknown, never as Escape followed by printable tail. Test fragmentation
at every byte boundary and variable emulator encodings. Do not echo unknown controls.

Bracketed paste and overflow reset hidden matching and never count as keys. Drain
all input at state boundaries, including animation completion, to prevent queued
keys from crossing two doors. Preserve exact password paste and separate Enter
submission. Unbracketed pasted bytes and synthetic key injection cannot always be
distinguished from typing; document that limit rather than claiming physical proof.

The Kitty keyboard protocol can report richer events, including lock keys, if
negotiated, but adopting it is optional future work and would require push/pop and
suspend restoration tests. This upgrade must work without it.
[Enhanced terminal keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/)

## 5. State-machine proposal

Keep the desktop and terminal lifecycles separate. An enum should not imply that
Relay owns an image viewer before it has launched.

```text
imv: INELIGIBLE ⇄ ELIGIBLE / matching
                       │ complete sequence + current snapshot
                       ▼
                  one-shot launcher
                       │
Relay: INSPECTOR_COVER ──hidden input──▶ VAULT_BUILD
              ▲                            │ completion + input drain
              │                            ▼
              │                         VAULT_WAIT
              │                            │ final hidden input
              │                            ▼
              │                         VAULT_FADE
              │                            │ completion + input drain
              │                            ▼
              ├──────── sleep ─────────── ROUTE
              │                            │ open (fixed route action)
              │                            ▼
              │                       AUTHENTICATING
              │                            │ real password verification
              │                            ▼
              └──── lock / idle ──────── UNLOCKED

maintenance ──────────────────────────▶ AUTHENTICATING
```

Use terminal enum states `INSPECTOR_COVER`, `VAULT_BUILD`, `VAULT_WAIT`, `VAULT_FADE`,
`ROUTE`, `AUTHENTICATING`, `UNLOCKED`. Remove `WAKING` once its role is replaced.
The inspector and vault hold have different matchers. Wrong input stays in state
silently. Construction/fade consume ordinary input without skipping hidden boundaries.

`sleep`, authenticated `lock`, idle lock and resume return to the inspector after
closing any session and resetting controller, animation and input state. Resize
redraws the current state, resets a hidden prefix, and never advances it. Interrupted
authentication/suspension must not leave a session alive. Fatal storage/durability
errors after the real boundary remain visible and controlled as they are today.
Three failed passwords retain the real backoff behavior; no fictional punishment.

Ctrl+C, EOF, HUP and termination exit cleanly. `exit` ends only Relay's process;
it does not request an OS terminal-closing action. A terminal launched for this one
process can naturally close when its child exits. Direct `relay open` starts at
the inspector; maintenance remains the documented recovery from forgotten rituals.

## 6. Cover redesign

Render a neutral image/file inspector, with no logo, Relay version, kernel, uptime,
vault-related wording, help, prompt or cursor. Example layout only—the values below
are not measurements of a repository carrier:

```text
IMAGE INSPECTION UTILITY

SOURCE
------------------------------------
file        kitty.png
type        PNG
dimensions  3024 x 4032
channels    RGBA
profile     sRGB (declared)
depth       8-bit
extent      18.42 MiB

STRUCTURE
------------------------------------
chunks      17
chunk CRCs  valid

STATUS
------------------------------------
inspection complete
```

Add a small **public PNG inspection reader** in `image_info.py`, separate from the
cryptographic parser. It does not interpret `rvLt` payloads or call `Capsule`,
`Store`, authentication or manifest routines. Existing `png.scan` understands
carrier segment semantics and gives carrier-specific errors; using it directly
for cover diagnostics would couple presentation to protected infrastructure.
Do not relax or rewrite that parser to accommodate the inspector.

Data sources:

* Basename and byte size from a safely opened regular file, with identity recheck.
* Type from PNG signature, not extension or an external `file` subprocess.
* Dimensions, bit depth, color type and interlace from a validated IHDR.
* Color type 0/2/3/4/6 maps to grayscale/RGB/indexed/grayscale-alpha/RGBA. Treat
  `tRNS` transparency separately; indexed color is not automatically RGBA.
* `sRGB` means declared sRGB. A bounded, structurally recognized `iCCP` means
  embedded ICC, without printing arbitrary profile text or decompressing it.
  No recognized profile means unspecified, not guessed sRGB. Conflicting markers
  mean ambiguous. Do not expose EXIF, comments, location, text chunks or profile names.
* Count all structurally bounded PNG chunks, including unknown private chunks,
  without displaying their types, lengths or a private-chunk breakdown.
* Stream CRC checks across chunks, using bounded buffers. “Chunk CRCs valid” means
  exactly that; it does not mean AEAD authentication or full pixel-decoder validation.

These fields follow the public PNG structure; the inspector deliberately implements
only the listed bounded reporting subset. [PNG specification](https://www.w3.org/TR/png-3/#11IHDR)

Do not print `entropy nominal`: no useful honest meaning has been specified.
Do not print payload size, capsule UUID, object counts, generation, backup paths,
KDF information or any decrypted name. Real overall file size and chunk count can
still arouse suspicion; no fabricated small size or falsified count.

The public parser should validate lengths, IHDR combinations, ordering and limits,
reject truncated framing and cap work at the existing total-carrier envelope and
chunk-count limit. Never inflate IDAT or arbitrary metadata. Unknown chunks are
opaque bytes. Sanitize terminal controls, bidi/control formatting and filenames;
use ASCII fallback and width-safe clipping without a new Unicode layout dependency.

Show quick metadata first and `chunk CRCs checking` / `inspection in progress`
while a single bounded background read finishes. Poll results in the existing TTY
loop; do not block Ctrl+C/resize during a GiB scan. On completion, cache by file
identity for redraw, and display the actual outcome. Cancel/join work on exit or
source change. Do not reread a GiB file on every resize. Input may start matching
only after the initial display is ready; no queued startup bytes count.

Malformed input yields only `inspection unavailable` or `chunk CRCs invalid` as
appropriate, never exception text or carrier-specific diagnostics. No path supplied
or a standalone `.relayvault` gets a minimal generic file inspection with PNG-only
fields omitted; maintenance remains fully usable. An invalid image-door preflight
must never open a terminal merely to show that failure.

For narrow terminals collapse spacing and drop optional rows; always remain within
width minus one and available height. Large terminals retain readable column widths
and whitespace. The next vault scene, not the metadata table, scales to fill the
screen. Non-TTY invocation prints a static safe inspection and exits without input,
password prompts, animation or ANSI control sequences.

## 7. ASCII vault animation architecture

Add `vault_scene.py` with deterministic ASCII geometry and scene progression, using
the existing `Terminal` stream. One function builds a bounded cell grid and structural
groups from `(columns, rows)`; one timeline selects visible groups. No curses, GUI,
asset service, terminal image protocol, scene engine or background animation thread.

Large-layout sketch (the implementation scales this to approximately 85–95% of the
usable terminal, rather than printing this fixed thumbnail):

```text
  +---------------------------------------------------------+
  | +-----------------------------------------------------+ |
  | |  [==]  +-----------------------------------+        | |
  | |        |  +-----------------------------+  |        | |
  | |        |  |             |               |  |        | |
  | |  [==]  |  |          ---O---            |  |  ||||  | |
  | |        |  |             |               |  |        | |
  | |        |  +-----------------------------+  |        | |
  | |        +-----------------------------------+        | |
  | +-----------------------------------------------------+ |
  +=========================================================+
```

| Build phase | Approximate normal duration | Visual treatment |
| --- | --- | --- |
| Clear and settle | 0.15 s | Clear inspector, no flash |
| Foundation | 0.45 s | Draw baseline from center outward |
| Outer walls | 0.65 s | Raise left/right edges |
| Frame | 0.65 s | Join top and inset frame |
| Door slab | 0.85 s | Assemble segmented panels, not a scanline screenshot |
| Hinges and wheel | 0.70 s | Attach hinges, hub and spokes |
| Locking details | 0.50 s | Bolts and sparse rivets |
| Settle | 0.25 s | Clear transient copy, hold complete structure |

Normal build totals about 4.2 seconds; fade about 1.0 second. Tune after visual review.
Use monotonic deadlines and about 20 frames/second, drawing only changed runs where
simple. Poll input/signals at most every 25–50 ms. Do not sleep once per character;
size must not multiply the total duration. Cap render dimensions/work for absurd
reported terminal sizes and center within larger terminals.

One understated line may appear near completion: `structural integrity: probably fine`.
Erase it before silent hold. No spinner, percentages, fake decryption progress,
flashing, random color storms or claims about actual verification.

`VAULT_WAIT` has no blinking cursor or prompt. Recommend a short sequence of
non-character terminal keys for each hidden boundary, without Enter. Review-only
examples: inspector `Home, F8, End`; completed vault `Left, Right, Home`.
Do not lock these as defaults until owner review. Both are configurable, distinct
from one another and from the image door. Caps Lock/Fn are unsuitable here.

For fade, erase detail groups in reverse order, briefly dim the remaining frame,
then break walls into disappearing segments and remove the foundation. Draw the
route banner and prompt into newly cleared rows near the end. The route controller
does not accept commands until fade completes and input is drained. The apparent
terminal “beneath” the vault is a composed frame, not a hidden running shell.

Resize recomputes geometry from normalized phase progress, clears the old scene and
redraws within new bounds; it does not restart a multi-second animation or skip a
hidden wait. Use compact geometry below roughly 60×20, minimal door geometry below
32×12, and a clipped static frame in extremely tiny terminals. Restore the complete
appropriate scene when space returns. Hidden input remains usable at tiny sizes.

Effects-off draws the final vault immediately, still waits for the final hidden
input, then reveals the route immediately. No timing, dimming or erosion. A separate
accessible text presentation may replace art with a short static structural outline,
while retaining silent input boundaries; screen-reader users can also use maintenance.
Do not make reduced effects dependent on cryptographic behavior.

All screen ownership stays in `TTYInput`: alternate screen, bracketed paste and
cursor state restore in `finally`, including partial setup, broken pipe and signals.
Do not call `Terminal._tty_keyboard` from this flow. Suspension restores the TTY
before stop; resume drops any session and returns to inspector. SIGKILL cannot run
cleanup; document this conventional terminal limitation without claiming otherwise.

## 8. Terminal route redesign

### Topology and fast path

Three fixed pseudo-locations are enough: `/media`, `/channel/13`, and `/diagnostics`.
The owner fast path is **`peel` → `follow 3` → `open`**. `peel` is optional discovery;
the shortest path remains **`follow 3` → `open`**. No hidden prerequisite flag,
inventory, score, branching quest or command that actually mounts a filesystem.

```text
relay: local surface

relay:/media> peel

layer 0    image
layer 1    annotations
layer 2    none of your business
layer 3    sealed handoff

relay:/media> follow 3

handoff: local
channel: 13
distance: negligible

relay:/channel/13> open

AUTHENTICATION
Password verification is required to open the vault.
password:
```

The layer map is fixed fiction, not a report from actual PNG metadata. Use “image”
instead of “PNG” so direct standalone access does not invent a media format. Do not
use fake latency, entropy or checksums as measurements. The real boundary banner
is deliberately plain; once reached it may say vault/authentication/password.

### Complete command contract

| Location | Command | Result |
| --- | --- | --- |
| `/media` | `peel` or `inspect layers` | Fixed layer table above |
| `/media` | `follow 3` | Move to channel 13, no prerequisite |
| `/media` | `follow diagnostics` | Move to diagnostics |
| `/media` | `ls` | `layers  handoff  notes` |
| `/media` | `cat layers` | Same fixed layer table |
| `/media` | `cat handoff` | `destination=13` then `scope=local` |
| `/media` | `cat notes` | `The outer layer is doing its job.` |
| `/channel/13` | `open` | Return `authenticate` action; do no authentication itself |
| `/channel/13` | `inspect seal` / `cat seal` | `state=closed` then `release=external verification` |
| `/channel/13` | `ls` | `seal  etiquette` |
| `/channel/13` | `cat etiquette` | `Requests are accepted. Assumptions are not.` |
| `/channel/13` | `knock` | `no.`; remain in place |
| `/channel/13` | `knock --politely` | `better.`; remain in place, grants nothing |
| `/diagnostics` | `ls` | `link  maintenance` |
| `/diagnostics` | `cat link` | `transport=local` then `remote endpoints=none` |
| `/diagnostics` | `cat maintenance` | `No appointment required. No promises made.` |
| Any route node | `status` | Fixed location and `session=closed` |
| Any route node | `back` | Return to media; at media print `already at surface` |
| Any route node | `clear` | Clear and repaint current prompt |
| Any route node | `sleep` | Inspector, fresh matchers |
| Any route node | `exit` | Exit Relay cleanly |

Only these exact resources/arity combinations exist. Unknown command, path or option:
`command: unavailable`. Bad quoting retains `command: invalid quoting`. `follow 2`
is unavailable, not a puzzle hint. Numeric aliases such as `03` are not accepted.
Do not include a general argument-to-path translation or autocomplete against the
host. A small fixed `help` could be added later, but is not necessary for this route.

Keep the existing explicit `reset channel` incident as a compatibility command
with its current independently armed policy, returning to media and printing only
`link: reset`. Do not make it part of the fast path, exploration hints or mistakes.
The image launcher must never pass `--arm-os-actions`. Existing direct CLI arming
remains a separate deliberate choice. Tests retain the machine-action backstop.

The personality is terse and competent with occasional reluctance. One joke during
construction and optional jokes on exploration are enough. Authentication, storage,
recovery and integrity failures use accurate plain language. No fake corruption,
threats, timed penalties, shell impersonation or commands pretending to decrypt.

### Authentication interface, including the future hardware phase

The controller returns only an `authenticate` intent. Keep password collection,
retry policy and `VaultSession.authenticate` in the authentication/application
boundary; return a fully authenticated session or controlled failure/cancellation.
Presentation may receive status labels, never key bytes or a partially authorized
session. Moving `main.authenticate` to `auth.py` is optional only if it simplifies
this separation; do not build an authentication-provider registry now.

Future hardware work must version the actual protected-material policy and make
the hardware participate cryptographically in key release/derivation/unwrapping.
The precise YubiKey capability, primary/backup enrollment and offline recovery
construction require their own security design and format review. Every unlock
path—including maintenance/recovery—must enforce that future portable policy.
Local presentation JSON must not decide whether a required factor can be skipped.

For this upgrade there is one real factor, password, and no hardware success flag,
USB-presence test, fake prompt, factor placeholder or changes to KDF/AAD/capsules.
A future password-plus-hardware vault cannot simply reuse today's password-only
unlock and add a UI check afterward. Old password-only backups also remain a
separate recovery/security concern for that future phase.

## 9. Configuration changes

Keep owner presentation policy in `RELAY_HOME/preferences.json`, private and atomic.
Never embed these settings in the carrier, encrypted manifest, migration or backups.
Maintain the existing `RELAY_HOME`/legacy-home precedence and OS-action defaults.

| Setting | Proposed meaning / default |
| --- | --- |
| `version` | New local schema version 2, explicit v1 migration |
| `target` | Existing default CLI target |
| `image_door.enabled` | False until explicit enrollment |
| `image_door.carrier_path` | Absolute enrolled PNG path, distinct from optional general target |
| `image_door.viewer` | Fixed identifier for supported imv integration version |
| `image_door.image_binding` | Dimensions and ordinary-image-chunk digest |
| `image_door.region` | Pixel rectangle inside enrolled original image |
| `image_door.zoom` | Finite positive min/max renderer scale |
| `image_door.anchor` | Normalized expected center; proposed `[0.5,0.5]` |
| `image_door.tolerance` | Normalized x/y tolerance; proposed `[0.12,0.12]` |
| `image_door.min_visible_fraction` | Proposed 0.90 |
| `image_door.sequence` | Canonical token array, proposed eight-key sequence |
| `image_door.sequence_timeout_seconds` | 5 inter-key seconds |
| `image_door.terminal_profile` | Explicit fixed executable/argv profile; local proposal foot |
| `inspector_sequence` | Separate TTY-capable token array; owner-review default |
| `vault_sequence` | Separate TTY-capable token array; owner-review default |
| `terminal_sequence_timeout_seconds` | 5 inter-key seconds |
| `effects` | Existing boolean; false disables animation only |
| `animation_speed` | Bounded preset `slow`, `normal`, `fast`; normal proposed |
| `presentation` | `ascii` or accessible static `text` |
| `auto_lock_seconds` | Existing authenticated idle timeout, 300 seconds |
| `real_os_actions` | Existing policy, unchanged and never armed by doorway |

No arbitrary scripts, shell fragments, regexes for window matching, secrets or
authentication material. Validate sequence lengths (1–64), named-key capabilities,
finite numbers, rectangle bounds, min≤max, absolute paths and exact known fields.
Reject unknown versions. Set practical speed/timing bounds so configuration cannot
create a zero-delay busy loop or multi-minute animation.

On explicit schema migration, preserve the old `wake` as the inspector sequence
after normalizing named arrows; preserve target/effects/idle and OS policy exactly.
Do not reinterpret the old wake as an enabled desktop sequence. A chosen final
sequence must be established before adopting the new ritual; maintenance remains
available throughout. Migrate only local JSON, atomically, with a private old-policy
copy for reversal. This is not vault migration and must not touch `migration.py`.

Proposed explicit owner configuration verbs: enroll/disable the image door, set/reset
each of the two TTY sequences, and set effects/speed. A one-shot enrollment view
captures the current region/pose only on an explicit command; runtime matching has
no overlays. Never print sequences during normal startup or general status.
Changes produce new generated viewer rules atomically; already-open viewers should
require a restart in the initial version, keeping reload behavior explicit.

## 10. Security and threat analysis

| Layer | What it provides | What it does not provide |
| --- | --- | --- |
| Ordinary image and visual pose | Conceals the normal entry point from casual observation | Payload undetectability or image authenticity |
| Three hidden inputs and fictional route | Learned access ritual | Authorization, password strength or offline-attack resistance |
| Password and future genuine hardware factor | Real authentication/key access | Protection from an already compromised endpoint |
| Existing authenticated encryption and transactions | Protected contents, integrity verification, dependable commit/recovery behavior | Hiding file existence, sizes, copies or rollback |

Specific risks and responses:

* **Global key observation:** rejected. No input-device permissions, root, XRecord,
  desktop listener or raw history. The viewer already receives its own keys; the
  matcher retains only bounded state for the configured context.
* **Viewer attack surface:** decoding an untrusted image can compromise that process.
  The integration holds no passwords/keys and never opens an authenticated session.
  Keep imv and decoders updated, pin/test the adapter, and retain maintenance if the
  optional integration is unavailable. This is not a sandbox against same-user code.
* **Spoofed windows/events:** titles/app IDs are not credentials. Internal focus and
  exact load state prevent accidental desktop triggering. X11 injection, privileged
  automation or malicious owner-local software can bypass concealment.
* **Background services:** none introduced. The short launcher has no network, logs
  or command interpreter. Its private runtime lock is not an authentication token.
* **Carrier replacement:** bind displayed generation and path; invalidate on edits,
  reload after atomic commits. The visual digest does not bind encrypted identity.
  Preserve the core's existing source-change and authenticated integrity checks.
* **TOCTOU:** preflight cannot freeze the desktop or hostile filesystem. Recheck at
  each handoff, fail quietly before cover, and retain real errors after authentication.
  Do not weaken store locks to keep the visual story smooth.
* **Process/desktop evidence:** imv integration files, `relay`, terminal argv, runtime
  locks and local preferences reveal the feature to process/file inspection. Titles
  should be neutral, but do not rename binaries to evade system tools or claim secrecy.
* **Filesystem evidence:** carrier extent/private chunks, backup directories, mtimes,
  file-manager recent items and thumbnails may expose unusual activity. Do not erase
  unrelated history or falsify metadata. Existing backup retention stays intact.
* **Malicious names/metadata:** strict public-field whitelist and terminal-safe rendering;
  never interpolate paths into shell commands, ANSI/OSC controls or resource handlers.
* **Concealment denial of service:** missing key, changed image, unsupported backend,
  malformed preferences or interrupted animation can stop the ritual. Explicit reset
  and direct password maintenance provide recovery without modifying the carrier.
* **Launch storms:** one target lock, per-viewer consumed attempt and bounded retry;
  no new terminal for wrong/partial input or unsupported contexts.
* **Machine actions:** no action from a hidden key or failure. Preserve all existing
  policy gates and automated execution prohibition, including future launcher tests.

Do not claim that this design protects a password entered into a malicious terminal,
prevents screen recording, defeats root, securely erases RAM or makes backup copies
disappear. Those are outside the concealment layer's capabilities.

## 11. Testing strategy

### Safe baseline and regression

Keep `tests/conftest.py`'s execution backstop active. Expand it to cover the new
launcher interface and child-process tests: recorded launch calls in unit tests,
disposable PTY children for integration, and no real logout/reboot/shutdown/terminal
closing. Do not whitelist `kitty`, `kitten`, `systemctl` or `loginctl` to make tests
pass. Viewer tests run under an isolated nested/headless display with a recording
launcher; never synthesize input into the owner's live desktop.

Run relevant tests and fix failures after each ordered stage. Finish with the entire
production and historical suite, installed-wheel journey, fresh-home maintenance
and updated release evidence. Existing crypto, known-answer capsule, PNG decoder,
transaction failure, backups, recovery, migration and password tests remain intact.
Update intentional presentation assertions; do not delete safety assertions merely
because the old route text changed.

### Concrete groups

| Group | Required high-value cases |
| --- | --- |
| Viewer key mapping | Home, End, PgUp, PgDn, Insert, Delete, Escape, CapsLock, F1–F12, arrows, Pause; supported/absent F13–F24; modifier/lock changes; initial press vs repeat/release; held key on focus entry |
| TTY decoder | CSI/SS3 variants; lone Escape vs incomplete CSI; every byte split; malformed/oversized escapes; UTF-8; bracketed paste split terminator/overflow; CapsLock unavailable rejected by settings; reserved interrupt keys |
| Matcher | Prefix/overlap, wrong interposed key, exact timeout boundary, repeated keys, independent state matchers, no cross-state buffered input, paste reset, no retained raw history |
| Door positive | Enrolled path + stable loaded image + eligible geometry + exact sequence launches once |
| Door negative | Correct image/wrong zoom, wrong viewport, wrong image/correct sequence, unsupported/stock viewer, console/slideshow/loading, invalid numeric geometry, missing config |
| Door lifecycle | Viewer closes mid-sequence; focus leaves/returns; different windows each type half; keyboard seat/keymap changes; resize/pan between keys; failed helper; missing terminal; rapid complete matches |
| File identity | Rename; atomic replace before load/during load/during match/before launch; in-place edit; stale displayed pixels; same basename; symlink component/swap; hard link; another copy; legitimate Relay commit then reload |
| Geometry | Region coverage/anchor edge tolerances, image letterboxing, zoom interval endpoints, 1×/2×/fractional scale, negative offscreen offsets, orientation/flip rejection, large window and tiny crop |
| Platform | Native Wayland focus/repeat, native X11 focus/synthetic/repeat mapping, separately qualified XWayland; missing/unrecognized keymap fails closed |
| Inspector | Actual IHDR fields across color/depth types, tRNS, sRGB/ICC/unspecified/conflicting profiles, exact size/count/CRC, arbitrary rvLt content never displayed, injected terminal escapes, truncated/bad CRC/oversized PNG, standalone and non-TTY |
| Inspector workload | Cancel long scan, resize uses cache, file changes during scan, no unbounded allocation or metadata decompression, no crypto/session calls before authentication |
| Animation | Golden geometry at several sizes; deterministic phases/deadlines; no route until fade complete; hold has no prompt/cursor; resize each phase; effects-off still needs final input; tiny/huge terminals; slow output bounded work |
| Terminal cleanup | Real PTYs: termios/alternate-screen/cursor/paste restoration on normal exit, Ctrl+C, EOF, HUP, TERM, exceptions, broken pipe, suspend/resume from every state; no second TTY reader |
| Route | Two-command shortest path, three-command descriptive path, exact exploratory copy, back/sleep/exit/clear, wrong arity, no discovery prerequisite, knock never authenticates, existing gated incident |
| Route isolation | `ls /`, `cat /etc/passwd`, `../`, `cd`, `env`, backticks, `$()`, semicolons, pipes, redirects and newlines; filesystem/subprocess functions patched to fail if controller touches them |
| Authentication | Explicit banner, never echo password, exact pasted password + separate Enter, wrong password/backoff independent of effects, no session before successful existing authentication, cancellation/idle lock, maintenance still bypasses only ritual |
| Configuration | v1 migration preserves policy; invalid/oversized JSON; unknown viewer/version/token; finite bounds; failed atomic write; no implicit enablement; rules round-trip/path injection; disable/restart clears state |

Manual acceptance, on disposable carriers only: ordinary image appearance, plausible
inspector, comfortable pose tolerances, Caps Lock side effect, physical keyboard
availability, most-of-terminal assembly, sparse humor, terminal focus behavior,
effects-off accessibility and screen restoration. Record tested viewer revision,
image decoder, compositor/backend, terminal and keyboard. Unit mocks establish logic;
they do not qualify an actual viewer integration.

## 12. Ordered implementation stages

The original review authorized Stages 0 and 1; the owner subsequently authorized
all remaining Stages 2–8 after Stage 1B passed. The implemented viewer is Swayimg.
See the implementation verification record for completed subtasks and design
adjustments; this table preserves the ordered experience goals.

| Stage | Goal and likely files | Tests | Completion criteria / dependencies |
| --- | --- | --- | --- |
| 0. Accept scope and establish baseline | Amend `IMPLEMENTATION_PLAN.md`; retain this reviewed plan; add experience verification record | Full existing suite and safe-execution audit | Accepted viewer-maintenance tradeoff, sequence policy and untouched-core boundary; no unresolved baseline failures |
| 1. Qualify viewer observations | Disposable imv patch/probe under `integrations/imv/`; native backend hooks, load identity and geometry | Isolated viewer harness for focus, raw keys, repeat, path reload, transforms and DPI; no real Relay launch | Demonstrate all required observations on Wayland; qualify X11 separately. Pin revision, size/review patch, prove source-generation binding. Depends on 0; stop and revise design if unsafe/too large |
| 2. Extend tokens and local settings | `input.py`, `settings.py`, configure handling in `main.py`; shared declarative matcher cases | Decoder/matcher/settings tests, PTYs, v1 migration/policy preservation | Rich named keys, explicit TTY capability rejection, old wake preserved, door remains disabled. Depends on 1 |
| 3. Ship scoped image match and launcher | `integrations/swayimg/`, small `door.py`, CLI precondition handling; install/disable documentation | Positive/negative geometry/file cases, multi-window/replacement/focus races, recorded argv/launch failures, no shell/network/input-device access | Correct visual state is necessary for a viewer launch; exactly one terminal request; silent failures; no daemon. Depends on 2 and platform qualification |
| 4. Replace inspector cover | `image_info.py`, `cover.py`, narrow `main.py` integration | Public PNG metadata/CRC/fuzzed bounds, no disclosure, scan cancellation, narrow/large/non-TTY | Honest real image fields; no capsule interpretation; responsive cover with no prompt. Depends on 3 |
| 5. Add terminal states and construction/hold | `access.py`, `main.py`, `vault_scene.py`, minimal rendering methods in `terminal.py` | Deterministic build, second sequence, state drains, resize/tiny layout, interruption/effects-off PTYs | Full-size assembled vault reaches silent hold; one input owner; no accidental advancement. Depends on 4 |
| 6. Final hidden input and dissolve | Same presentation modules, `input.py` only if a tested gap appears | Final sequence, reverse groups, frame timing, mid-fade resize, queued input, resume | Vault dissolves into route; controls restored; effects-off preserves boundaries. Depends on 5 |
| 7. Route copy and real auth boundary | `topology.py`, `access.py`, `main.py`; optional minimal movement of existing auth function | Exact route contract, no host access/execution, real password/backoff/session PTYs, preserved incident gates | Short path and exploration feel coherent; auth clearly real; no crypto or fake hardware changes. Depends on 6 |
| 8. End-to-end qualification and owner docs | README, verification docs, installed-wheel script, optional integration packaging | Full suite; installed package; disposable viewer→terminal→password→store→lock→reload journey; existing decoder/backup/recovery/migration checks | Supported matrix recorded, enable/disable/reset/maintenance explained, core regression intact, reviewed visual acceptance. Depends on 7 |

Each implementation stage must be independently reviewable and leave maintenance
functional. No format bump, crypto dependency change or transactional-storage edit
is expected. If a concrete incompatibility demands one, explain it and reopen the
scope before changing the core. Do not use future YubiKey work as justification for
new provider frameworks or portable metadata in this phase.

Completion requires all accepted stages, the full safe test suite, the installed
journey and real isolated viewer evidence. A mocked focus/zoom response or a working
ASCII animation alone does not complete the experience.

## 13. Open decisions for owner review

Only product/policy choices remain for the owner; API gaps and platform behavior
belong to the implementation feasibility tests.

1. **Resolved: maintain the small optional imv integration build.** The owner
   approved this cost, subject to the Stage 1 feasibility/patch-size gate. Do not
   substitute screen scraping or a global listener.
2. **Actual carrier and pose:** choose the PNG and meaningful image region during
   enrollment. The rectangle/zoom cannot responsibly be invented without that image.
3. **Resolved: preferred first sequence uses Pause and Caps Lock.** Recommend
   Insert only if physical testing shows Pause is unavailable. Record the actual
   Caps Lock behavior without synthesizing corrective input.
4. **Two terminal sequences:** approve the no-Enter named-key mechanism and choose
   distinct actual sequences. `Home,F8,End` and `Left,Right,Home` are examples only.
5. **Experience copy:** accept the `peel / follow 3 / open` vocabulary, optional
   `knock` exchange and approximately 4.2-second construction, or adjust before
   snapshot tests make the copy a contract.

Recommendations already made without requiring more owner input: keep maintenance,
one TTY owner, no global capture/daemon, normal imv behavior outside eligibility,
effects-off support, local-only presentation policy and the current real OS-action
gates. Stage 1 work is isolated development instrumentation, not a production doorway.
