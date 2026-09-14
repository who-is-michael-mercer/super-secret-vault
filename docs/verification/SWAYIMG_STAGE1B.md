# Stage 1B — Swayimg viewer qualification

The original Pause attempt below is historical. The owner subsequently approved
PrtSc and the screenshot-shortcut relocation; see the continuation at the end.
**Current result: STAGE 1 PASSES — Swayimg recommended for the visual door.**
This is qualification of the documented native Wayland development profile, not
authorization for Stage 2 or a claim of general production readiness.

Date: 2026-09-13. Branch: `v3/design`. Starting repository revision: `f332819`.
Authorization: Stage 1B alternative evaluation only. Stage 2 remains unauthorized.
The imv Stage 1 record and completed original V3 stages are preserved.

## Scope and environment

No production Relay source, cryptography, capsule formats, storage, migration,
backups, recovery, password handling or later presentation states were changed.
No real logout, reboot, shutdown or terminal-closing action was executed. The
existing `tests/conftest.py` process audit guard remained enabled.

Fresh full-suite command: `.venv/bin/python -m pytest -q`.
Actual result: **1,321 passed in 25.95 seconds**.

| Item | Observed value |
| --- | --- |
| Distribution | Omarchy 4.0.2, Arch-derived (`/etc/os-release`) |
| Kernel / architecture | Linux 7.1.9-arch1-2, x86_64 |
| Session | Native Wayland, Hyprland 0.56.2 |
| Hyprland commit | `efb50993780079460b0cbed1363e2166a2de1d9f` |
| Endpoints | `WAYLAND_DISPLAY=wayland-1`, `DISPLAY=:0` |
| Python | 3.14.7 |
| Compiler | GCC 16.2.1, C++20 |
| Build tools | Meson 1.12.0, Ninja 1.13.2 in `/tmp/relay-swayimg-tools` |
| Native dependencies | Wayland client 1.26.0, protocols 1.49, xkbcommon 1.13.2, Lua 5.5.1, libpng 1.6.58, fontconfig 2.18.3, FreeType pkg-config 26.6.20 |
| Installed Swayimg | None on PATH at start; only the isolated build was used |

The source checkout and build tools were downloaded into `/tmp` with explicit
sandbox escalation. GUI tests were likewise explicitly approved. No system
packages, file associations, desktop configuration or startup services changed.
DRM and Swayimg's optional compositor integration were disabled at build time.
There was no compositor IPC, global shortcut listener, `/dev/input`, desktop
polling, screen scraping, keyboard synthesis or network service in the probe.

## Initial source/API findings and patch

Exact tested source: [Swayimg commit 7e7590a](https://github.com/artemsen/swayimg/tree/7e7590a19ab5e93f1272ecb810e47f4d8a163549),
described by Git as `v5.6-9-g7e7590a`; binary reports
`5.6-9-g7e7590a-dirty` because it includes the development patch.

Stock Lua supplies active path/image dimensions, scale, pan, buffer dimensions,
image-change, resize and completed-redraw hooks. Stock Lua **does not satisfy the
full contract**: key callbacks conflate initial press with repeat, do not receive
release, and do not expose focus enter/leave or held keys on entry. Image metadata
comes from a list entry and does not establish cached decoded-file identity.
These conclusions come from the pinned `src/luaengine.cpp`, `src/ui_wayland.cpp`,
`src/xkb.cpp`, `src/formatfactory.cpp`, `src/viewer.cpp` and
[API documentation](https://github.com/artemsen/swayimg/blob/7e7590a19ab5e93f1272ecb810e47f4d8a163549/CONFIG.md).

Before implementation the proposed patch was estimated at 180–220 added lines.
The actual patch is **124 added / 3 removed lines across 10 upstream files**:

| File | Added / removed | Purpose |
| --- | --- | --- |
| `src/appevent.hpp` | 4 / 1 | Development event in existing application queue |
| `src/application.cpp` | 10 / 1 | Deliver observer events on Lua thread; invalidate on viewer events |
| `src/application.hpp` | 1 / 0 | Observer callback |
| `src/formatfactory.cpp` | 39 / 0 | Opt-in bounded descriptor-stamped file snapshot |
| `src/image.cpp` | 3 / 0 | Reject original-coordinate matching after transforms |
| `src/image.hpp` | 2 / 0 | Provenance attached to decoded pixels |
| `src/luaengine.cpp` | 17 / 0 | Event/time functions and origin fields |
| `src/relay_probe.hpp` | 31 / 0 | File stamp and current-identity check |
| `src/ui_wayland.cpp` | 16 / 1 | Raw press/release/repeat, focus, held-entry and keymap notifications |
| `src/xkb.hpp` | 1 / 0 | Raw repeat code for diagnostics |

The patch applies cleanly to an archive of the exact upstream pin. All ten patched
files byte-match the tested checkout. Upstream and repository whitespace checks
passed. Reproduction scripts, Lua probe, tests, license and evidence are under
[`integrations/swayimg/`](../../integrations/swayimg/README.md).

## Geometry, focus and image identity: actual Wayland results

`python integrations/swayimg/wayland_check.py ... --report ...` passed **15 actual
Wayland window checks**. It used fixed supported Lua view commands through the
test viewer's signal handler; it sent no key events. Every snapshot had zero
sequence matches and `eligible=false`, as required without physical sequence input.
The final run explicitly seeded a **partial prefix only** before view, file and
focus changes and asserted that it returned to zero. Zoom/pan/transform/resize
operations seed inside the fixed Lua callback, after the signal event's generic
reset, so the subsequent real view/redraw hooks must clear it. No test seeds a
completed sequence. This instrumentation is gated by `RELAY_SWAYIMG_TESTING=1`
and is absent from the physical-session runner.

| Check | Actual outcome |
| --- | --- |
| Native viewer, active image, dimensions, focus | Qualified; initial visual predicate true |
| Zoom outside 0.9–1.1 | Visual predicate false |
| Pan outside configured tolerance | Visual predicate false |
| Same basename in another directory | Other exact path observed; rejected |
| Image switch back through history | Original decoded generation observed and qualified |
| Rename while pixels remain displayed | Current identity false; rejected |
| Rename back and explicit reload | New decoded generation qualified |
| Atomic replacement preserving mtime | Old displayed generation remained unchanged and was rejected |
| Switch away/back to stale history entry | Cached old generation remained rejected |
| Explicit reload of replacement | New generation/stamp qualified |
| Rotation | Original-coordinate predicate rejected |
| Mirroring | Original-coordinate predicate rejected |
| Fullscreen resize/redraw | Buffer dimensions changed, geometry recomputed and qualified |
| Second viewer takes focus | First viewer observed actual focus leave |
| Second viewer closes | First viewer observed actual focus return |

See [the measured snapshots](../../integrations/swayimg/evidence/wayland.json).
The API reports buffer-pixel dimensions; scale/pan/region math uses those units.
The redraw boundary means a frame submitted by the viewer, not exact physical
display scanout. Fractional scaling across different monitors was not tested.

The headless check links the **real patched loader and PNG decoder**, and passes
six groups: exact path/same basename, rename/reload, replacement preserving mtime,
symlink/hardlink rejection, all three transforms, and truncation with safely
retained decoded pixels. File snapshots are capped at 16 MiB in this development
profile. The decoded stamp is never refreshed from a newly replaced pathname.
History caching therefore cannot incorrectly bless stale pixels.

## Input and reset evidence

Ten deterministic Lua checks pass: preferred full sequence, all eight code
counters/Pause preservation, repeat/duplicate press rejection, prefix overlap and
wrong keys, timeout/retry, focus/held-entry release gating, keymap reset without
invented focus loss, partial resets for view boundaries, visually ineligible full
sequence rejection, and geometry/path/stale/transform rejection. These are
synthetic **in-process unit calls**, not physical-key evidence or desktop injection.

The first physical session received press/release events for HOME, F7, END, PGUP,
CAPSLOCK, ESC and INSERT, plus Home repeats. PAUSE had no events. The owner then
explicitly reported: **“I dont have a pause key.”** No missing-key inference was
made merely from zero counts. Insert was recommended as an explicit fallback;
the default preferred sequence retains Pause.

| Requested physical key | Initial presses | Releases | Repeats observed | Result |
| --- | ---: | ---: | ---: | --- |
| KEY_HOME | 6 | 6 | 64 | Delivered |
| KEY_F7 | 3 | 3 | 0 | Delivered; repeat not physically exercised |
| KEY_END | 3 | 3 | 0 | Delivered; repeat not physically exercised |
| KEY_PAUSE | 0 | 0 | 0 | Owner reports no Pause key |
| KEY_PGUP | 3 | 3 | 0 | Delivered; repeat not physically exercised |
| KEY_CAPSLOCK | 3 | 3 | 0 | Delivered |
| KEY_ESC | 3 | 3 | 0 | Delivered; repeat not physically exercised |
| KEY_INSERT | 4 | 4 | 0 | Delivered separately; not substituted into sequence |

The exploratory first run is retained as
[`physical-first-run.json`](../../integrations/swayimg/evidence/physical-first-run.json).
It predates two fixes and does not qualify the complete predicate: keymap changes
were incorrectly represented as focus loss, and unchanged pointer events could
leave the redraw gate blocked. Both were corrected. Current keymap events reset
only the prefix and preserve real focus/held-key state. Unchanged pointer events
reset the prefix while actual pose changes must match a completed redraw.

The full physical predicate remains unverified. The owner choice of an explicitly
labeled Insert fallback was requested; no answer had arrived at this stopping
point. No fallback profile was implemented or silently enabled. No successful
Pause or Insert sequence is claimed.
The [corrected-run snapshot](../../integrations/swayimg/evidence/physical-corrected-run.json)
is retained separately. All disposable viewer children exited or were closed;
no probe service was installed or left running.

## Qualification limits and stopping verdict

* **Native Wayland:** source, geometry, real focus transitions, file identity and
  partial invalidation tests pass on the current Hyprland environment.
* **Physical sequence:** incomplete. Seven keys deliver, but this keyboard has no
  Pause key. The preferred sequence cannot complete as physically tested. A
  separately approved Insert fallback needs a fresh physical success on the final
  probe before the complete contract can pass.
* **Held before focus:** real Wayland entry arrays are forwarded; deterministic
  gating tests pass. No physical held-before-focus entry was observed, so that
  part of physical qualification also remains open.
* **Release/repeat:** separately observed for Home; press/release observed for the
  other available requested keys. No claim that every key repeats or that all
  repeat/focus races have been physically exercised.
* **File scope:** disposable PNGs and canonical owner-owned regular files under
  16 MiB. Production-size carrier performance, hardlink/symlink convenience,
  automatic reload and fractional/multiple-monitor scaling are unqualified.
* **X11/XWayland:** not tested or supported by this build. `DISPLAY=:0` is not
  evidence of qualification; Swayimg uses the native Wayland backend here.
* **Security:** checks provide concealment, not authentication. Path/stat stamps
  are not a defense against malicious owner/root code. Observable process names,
  local Lua config and development evidence reveal the integration to the owner.
  Password and existing encryption retain their roles. No core incompatibility
  or reason to change cryptography/storage was found.

Swayimg is a promising, substantially smaller integration than the imv probe,
but the required **full physical eligibility predicate has not passed**. This
verdict reflects the incomplete keyboard gate, not a demonstrated failure of
Swayimg's visual-state observation. No Stage 2 work was performed.

**STAGE 1 DOES NOT PASS — viewer-local strategy needs reconsideration**

## Owner-approved PrtSc continuation

The owner explicitly selected **PrtSc instead of Pause**, chose **Shift + PrtSc**
for screenshots, and instructed implementation of the reviewed qualification plan.
The new sequence is HOME, F7, END, PRTSC, PGUP, CAPSLOCK, ESC, HOME. The probe uses
Linux `KEY_SYSRQ` code 99; `KEY_PRINT` code 210, Pause and Insert are not aliases.
The original captures above remain unchanged.

Changes are confined to the development probe/tests/documentation and the approved
local shortcut override. The final patch is **125 added / 3 removed lines across
11 files** at the same pinned revision. The additional upstream change is one line
in `src/text.cpp`: request redraw when clearing a status message. All other file
counts in the initial patch table remain unchanged.
No production Relay module, crypto/storage code or Stage 2 feature changed.

### Screenshot shortcut

Backed up the exact user config to:
`/home/michael/.config/hypr/bindings.lua.relay-stage1b-1789321854127886839.bak`.
Added `hl.unbind("PRINT")` and the screenshot action on `SHIFT + PRINT` in
`~/.config/hypr/bindings.lua`. No packaged Omarchy file was modified.

`hyprctl reload` returned `ok`; `hyprctl configerrors` returned no errors.
The active binding list confirms Shift + PrtSc for screenshots, no bare PrtSc
binding, and the existing Super/Alt/Super+Ctrl PrtSc actions preserved.
This is relocation of the existing screenshot action, not a global Relay handler.

### Automated results

* Full existing suite: **1,321 passed in 26.99 seconds**.
* Ten Lua matcher/geometry groups passed, including explicit PrtSc selection and
  rejection of Pause, Insert and AC Print substitutions.
* Six headless groups passed against the real pinned PNG loader.
* Sixteen live Wayland checks passed with the PrtSc matcher and partial-state
  invalidation seam; [recorded snapshots](../../integrations/swayimg/evidence/wayland-prtsc.json).

The first live rerun exposed a test-harness race: immediately toggling fullscreen
back could read stale fullscreen state and seed a prefix before resize completion.
The harness now explicitly requests fullscreen on/off and waits for the restored
window dimensions before testing focus invalidation. The corrected rerun passed
all 15 checks. This required no viewer or production change.

Physical testing then exposed an upstream display issue: `Text::set_status("")`
cleared the status internally but returned without requesting a redraw, allowing
the old `ELIGIBLE` pixels to remain after the predicate became false. Added the
one-line redraw request and a live test that displays a neutral test status,
clears it, and verifies another completed frame. This brings the final live suite
to 16 passing checks. The first PrtSc session's actual match and counters are
preserved as [pre-redraw-fix evidence](../../integrations/swayimg/evidence/physical-prtsc-before-redraw-fix.json),
not used to claim a second successful match from a stale label.

The rebuilt patch applies cleanly to the pinned upstream archive; all 11 patched
files byte-match the tested source. The ten Lua and six headless groups were rerun
successfully after the fix. The full Relay suite result above remains applicable;
`git diff --exit-code -- src tests` confirms no production or existing test changes.

The physical runner now keeps one overwritten `last-success.json` containing the
last fully eligible pose and aggregate counters. It does not store ordered keyboard
events. Automated tests cannot create it because they never complete a sequence.
Physical sequence, focus/held-key and screenshot-picker acceptance were performed
on the explicit disposable viewer; the passing gate is supported by physical
events and owner confirmation, not inferred from the automated checks alone.

On the final rebuilt viewer, **three complete physical PrtSc sequences were recorded**
with valid image identity, qualifying geometry and focus. The owner confirmed the
label appeared, disappeared after expiry, and reappeared after the second sequence.
The owner then held Home across a focus leave/return, tapped F7 while Home remained
held, released the keys, and entered a fresh full sequence. The final snapshot
records one held-entry event, one blocked-held press, 25 Home repeats, and the
third successful match after release. The owner confirmed “it all works” in response
to the explicit held-key/recovery and screenshot-picker/cancel checks.

### Final physical evidence and verdict

The [final physical capture](../../integrations/swayimg/evidence/physical-prtsc.json)
contains the final aggregate snapshot, the most recent actual `eligible=true`
snapshot, selected sequence/code and owner confirmations. It contains no ordered
keyboard history and no synthesized input. Final per-key observations:

| Key | Presses | Releases | Repeats | Evidence |
| --- | ---: | ---: | ---: | --- |
| HOME | 8 | 8 | 25 | Final rebuilt viewer |
| F7 | 5 | 5 | 0 | Final rebuilt viewer |
| END | 3 | 3 | 0 | Final rebuilt viewer |
| PRTSC / KEY_SYSRQ (99) | 3 | 3 | 0 | Final rebuilt viewer |
| PGUP | 3 | 3 | 0 | Final rebuilt viewer |
| CAPSLOCK | 3 | 3 | 0 | Final rebuilt viewer |
| ESC | 3 | 3 | 0 | Final rebuilt viewer |
| INSERT | 4 | 4 | 0 | Earlier Stage 1B physical capture; no Insert event recorded in final run |

Pause remains unavailable on the owner's keyboard and was explicitly superseded;
Insert is not part of the chosen sequence. A zero repeat count does not establish
that a key cannot repeat. Initial presses and releases were observed for every
sequence key, and repeats were physically exercised with Home.

The corrected observer never completed a match for the held-key attempt. Fresh
input after release succeeded. Actual focus transitions and pose/file invalidations
were also covered by the live checks; both expiry and negative state clear the
visible status with the new redraw fix. Shift + PrtSc opens the screenshot picker
and the owner confirmed canceling with Esc; no automated screen capture was used.

All disposable viewers were closed after evidence capture. The screenshot override
remains installed as explicitly approved; its backup path is recorded above.
No Relay process, daemon, global input observer, production launcher or later
presentation state was introduced. Cryptography/storage and the existing Python
tests remain unchanged.

Remaining qualification limits are the deliberate 16 MiB development file cap,
disposable PNGs/canonical paths, one current native Wayland/Hyprland environment,
and no X11/XWayland or cross-monitor fractional-scale qualification. The core still
supports its original carrier sizes; production-size performance and automatic
reload belong to later work. These limits do not invalidate the demonstrated
viewer-local predicate, and are not claims of cryptographic security.

**STAGE 1 PASSES — Swayimg recommended for the visual door**
