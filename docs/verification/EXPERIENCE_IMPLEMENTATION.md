# Experience implementation — Stages 2–8

Branch: `v3/design`. Owner authorization: 2026-09-14, all remaining stages.
Original V3 completion and Stage 0/1/1B evidence remain in their existing records.
Baseline: 1,321 tests passed (Stage 1B, 26.99s). No machine actions in tests.
Crypto, capsule, PNG storage, transactions, backups, recovery, migration and
VaultSession are frozen unless a concrete incompatibility is recorded first.

## Stage 2 — input and local policy
- [x] Decode named terminal keys, distinguish bare Escape, preserve paste/drains.
- [x] Validate v2 settings; migrate v1 without changing legacy wake or OS policy.
- [x] Expose owner configuration and reject impossible terminal sequences.
- [x] Focused input/settings/CLI tests and full regression.


Result: **complete**. Focused legacy input/settings/CLI: 26 passed; full regression:
**1,374 passed in 42.35s**. Added fragmented CSI/SS3/Home/End/F1–F12 decoding,
bare-Escape expiry, paste reset and line editing. Settings v2 migrates v1 in memory
and writes atomically on configuration changes. Terminal sequences cannot request
Caps Lock, Print, Pause or modifiers: classic terminal protocols cannot deliver
those reliably. Terminal repeat is indistinguishable from another press; the
default sequences have no adjacent duplicates. Bracketed paste never wakes.
PrtSc product token maps to raw code 99 only. No core changes.

## Stage 3 — scoped Swayimg doorway
- [x] Promote the qualified hooks with bounded production carrier loading.
- [x] Enroll ordinary-image identity and geometry; install local viewer configuration.
- [x] Minimal viewer-only matcher, fixed-argv launch and duplicate/race guards.
- [x] Identity, focus, event and geometry tests; full regression and live checks.

Result: **complete**. Focused door/input/CLI: 66 passed; shipped Lua: 2
passed. Full regression: **1,382 passed in 28.05s**. Both the historical and
production matcher pass ten Lua groups. Native decoder: six historical + seven
production groups, including a >16 MiB payload with bounded ordinary-PNG decoding.
Sixteen live Wayland checks pass on each loader mode; the shipped configuration
and inherited request socket also pass in a real viewer. New patch: **179 added /
3 removed lines, 11 upstream files**, same pinned revision. Prior physical-key
qualification remains owner-observed Stage 1B evidence, not a new automated claim.

Decisions: `image_info.py` was introduced here because enrollment and handoff need
public-image binding before Stage 4 can render it. It streams CRC checks without
capsule parsing. The viewer skips payload chunks on the same source descriptor
instead of copying a GiB carrier. No storage/core change was needed. The scoped
broker lives only with its viewer/Foot children; it is explicitly launched, never a
service. Requests contain a stat stamp only. Fixed argv and per-target advisory
locks prevent shell interpretation and duplicate terminals. Reload after an atomic
commit is deliberate. Production is silent; diagnostics remain development-only.

## Stage 4 — inspector
- [x] Independent bounded PNG metadata/CRC inspection, safe public fields only.
- [x] Responsive silent inspector with cached reads and malformed-file handling.
- [x] Cover correctness/limits tests and full regression.

Result: **complete**. Focused PNG/cover/CLI/door tests: 27 passed. Full
regression: **1,396 passed in 28.14s**. Public dimensions, channels, depth, size,
chunk count, CRC state and safely detected profile are real. No chunk names,
capsule values or fabricated entropy appear. ICC payloads are not decompressed or
displayed. Scans are bounded and cached per cover entry; resize performs no I/O.
Narrow layouts clip by display cells and terminal height; filenames/control bytes
are sanitized. Malformed/non-PNG sources show neutral incomplete inspection.

## Stage 5 — construction and silent hold
- [x] Scalable architectural ASCII scene with progressive construction.
- [x] Explicit states, resize/resume recovery, input boundaries and effects-off.
- [x] Scene/PTY tests and full regression.

Result: **complete**. Focused scene/PTY/CLI/input: 29 passed. Full regression:
**1,408 passed in 36.13s**. Layered housing, bevelled door, hinges, wheel and rivets
fill the terminal; normal build 3.6s, fast 1.4s, slow 5.4s. Effects-off and text
presentation are immediate but retain both hidden boundaries. Small screens use a
compact structure. Rendering avoids the terminal bottom/right cell, bounds extreme
sizes at 240x80 and redraws safely on resize. Construction polls the existing TTY
owner and discards input; hold resets its matcher on resize/resume. PTYs verify
restoration on interruption and that batched later-stage input cannot advance.
The preserved legacy first sequence is explicitly available via `open --legacy-wake`;
it still leads through construction/hold. Ordinary opens use the approved new keys.

## Stage 6 — dissolution
- [x] Final sequence and paced reverse assembly revealing the terminal.
- [x] Resize/interruption cleanup and no buffered input crossing states.
- [x] Transition tests and full regression.

Result: **complete**. Focused scene/input/CLI: 32 passed. Full regression:
**1,411 passed in 37.54s**. A separate VAULT_FADE state dims and reverse-assembles
the same deterministic canvas (normal .95s / fast .5s / slow 1.6s). The final frame
is erased before the route starts. Build/fade share a renderer and the same TTY
input owner. Resize redraws at current progress; all transition input is discarded
and boundary-drained. Effects-off erases immediately without skipping the final
hidden sequence. EOF/exception paths restore ANSI style and termios.

## Stage 7 — route and authentication
- [x] Coherent fixed topology, memorable fast path and restrained exploration.
- [x] Clear password boundary; preserve maintenance and incident safety gates.
- [x] Route isolation/auth/session tests and full regression.

Result: **complete**. Focused route/auth/input/scene/incident tests: 91 passed;
after the suspend correction, focused CLI/input: 72 passed. Full regression:
**1,439 passed in 37.92s**. Fast path `peel`, `follow 3`, `open`; `peel` is optional
when memorized. Media/channel/service contain fixed resources only. Tests replace
host filesystem and subprocess operations with failures while exercising hostile
commands. The real authentication screen is separate and contains no jokes.
Maintenance, retries, idle locking and separately gated incidents remain intact.

The first broad run exposed a pre-existing unsafe signal-handler I/O pattern:
SIGTSTP arriving inside buffered output could recurse into that writer. The handler
now sets a flag; the input-loop safe point restores/stops/resumes. Tests wait for an
actual stopped child before SIGCONT. Suspended password input cancels cleanly.
The failure was fixed and the full suite passed before advancing. No crypto/storage
code changed, and no new authentication/provider framework was introduced.

## Stage 8 — end-to-end qualification and owner handoff
- [x] Installed environment, disposable carrier, complete PTY journey.
- [x] Actual store/retrieve/lock/reopen; independent maintenance and cleanup.
- [x] Live viewer integration, setup/demo instructions and support limits.
- [x] Final focused/full regression, core diff audit and runnable handoff.

Stage 8 qualification tasks, in execution order:
- [x] Add cross-state PTY cleanup, resize and legacy-wake checks.
- [x] Extend installed-wheel qualification to store/retrieve/lock/reopen/maintenance.
- [x] Build a new wheel and verify it outside the checkout in a fresh environment.
- [x] Exercise native Swayimg -> socket -> broker -> real Foot -> real Relay,
      using an explicit test-only local event/PTY driver, never desktop key injection.
- [x] Create a private disposable owner demo and one-command launch script.
- [x] Audit file/argv/process lifetime and frozen-core differences.
- [x] Complete README/setup/troubleshooting, limits and owner feedback targets.
- [x] Run final focused checks and full regression; record exact results.

Stage 8 decisions and intermediate evidence:
- Cross-state checks now include SIGINT/SIGTERM/SIGHUP/EOF, actual PTY loss,
  resize during hold, and explicit legacy wake. Every normal PTY completion
  compares complete termios with its initial value.
- Installed wheel: 13 checks outside checkout in a fresh venv, including shipped
  Lua, complete animated ritual, store/retrieve, lock/reopen, maintenance,
  backup/recovery/verification and the legacy module shim.
- Live native chain: two Swayimg-local synthetic matches, two real Foot launches,
  three real password sessions, store/retrieve, stale-display rejection and
  explicit reload/reopen. This is not new physical input evidence.
- Final audit moved duplicate-launch locks into the owner runtime directory so
  different local profiles cannot duplicate a target's terminal. Added explicit
  decoded-image and PNG metadata allocation limits in the viewer only: 16,384
  pixels per side, 64 Mi pixels total. Static PNG remains the supported profile.
- Final viewer patch: 195 additions / 3 deletions across 12 files. A clean checkout
  of the exact pin accepts it, and all patched bytes match the compiled tree.
- Actual PTY disappearance exposed Python's final buffered-flush exit failure.
  The TTY owner now discards output on confirmed terminal loss, restores signal
  handlers and exits normally through the cancellation path. All three new
  terminal-loss cases (cover/password/unlocked) pass; no forced process exit or
  skipped session cleanup was introduced.
- The disposable owner demo is `.local/demo/evening.png`; public password 13001300.
  Its own `RELAY_HOME` and build artifacts are ignored by Git. Existing demo data
  is reused, never reset automatically. See `docs/EXPERIENCE_GUIDE.md`.

## Final qualification — 2026-09-14

**Stages 2–8 are implemented and engineering qualification passes.** The owner can
run the complete disposable experience now; subjective acceptance and physical
feel of the new terminal stages are feedback targets, not fabricated test results.

| Final check | Actual result |
| --- | --- |
| Focused Python experience suite | **179 passed in 59.43s** |
| Complete V3 regression suite | **1,474 passed in 86.31s**, no skips/failures |
| Fresh installed wheel outside checkout | **13 checks passed in 10.80s** |
| Final native Swayimg -> Foot journey | **passed in 8.86s**: 2 terminal launches, 3 real password sessions |
| Live Wayland observation checks | **16 passed** on the final production loader |
| Qualified and shipped Lua matcher groups | **10 + 10 passed** |
| Native upstream loader groups | **6 historical + 8 production passed** |
| Clean patch / compiled-tree comparison | **12 files match**, exact upstream pin |
| Frozen core / test safety guard diff | **no changes** |

The final live driver initially timed out correctly while the viewer was at 83%
scale and lacked focus. It had changed scale before image load completed. The
driver now sets the load-time scale policy, uses only its own viewer's fullscreen
mode during qualification, and waits for actual drawn geometry, focus and released
keys before feeding its explicitly synthetic local events. It sends no synthetic
focus or desktop key events. The corrected final run passed. Production still
opens an ordinary window with owner-controlled pose and native focus requirements.

The native journey used the shipped matcher/door Lua, the actual patched decoder,
the inherited datagram, production broker/identity checks/lock and real Foot.
Only test configuration wrapping and a nested PTY input driver supplied automation;
none is shipped as a production input seam. It stored/retrieved actual data,
locked/reopened in the terminal, rejected the stale viewer image after atomic
replacement, explicitly reloaded and launched/reopened again. Authenticated sessions
and test-created processes ended normally. Runtime advisory locks were released;
empty lock files intentionally remain safe to reuse. Temporary viewer configurations
were removed. No daemon/service, global key listener or system association exists.

Physical image keys remain the owner-confirmed Stage 1B qualification. No new
physical events are claimed by the automated run. X11/XWayland and other viewers or
terminal profiles are unqualified. Classic TTY repeats/unmarked paste cannot be
proved physical; bracketed paste and queued cross-state input are rejected. The
owner guide records decoded-image/size limits and explicit reload behavior.

Environment: Arch Linux, kernel 7.1.9-arch1-2, Python 3.14.7, cryptography 50.0.1,
pytest 9.1.1, Hyprland 0.56.2, Foot 1.27.0. Viewer: Swayimg
`7e7590a19ab5e93f1272ecb810e47f4d8a163549`, `5.6-9-g7e7590a` plus the reviewed
195-addition / 3-deletion patch. Build tools: Meson 1.12.0, Ninja 1.13.2, GCC 16.2.1,
Wayland 1.26.0 / protocols 1.49, Lua 5.5.1, libpng 1.6.58.

No logout, reboot, shutdown or terminal-destruction action ran. Tests used disposable
PTYs and owned viewer processes; Foot test windows exited via their normal child
exit. Existing owner terminals were left alone. Crypto/capsule/PNG storage,
transactions, backups, recovery, migration, VaultSession and authentication policy
remain byte-for-byte unchanged in this working tree. Future YubiKey work is deferred.

Reproduction and immediate owner walkthrough: [experience guide](../EXPERIENCE_GUIDE.md).
Machine-readable summaries: [final checks](experience-evidence/final.json),
[installed wheel](experience-evidence/installed.json),
[native journey](experience-evidence/native-journey.json).
The live geometry snapshots are under `integrations/swayimg/evidence/`.
