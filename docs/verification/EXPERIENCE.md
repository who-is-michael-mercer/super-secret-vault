# Relay experience verification

## Stage 0 — approved scope and passing baseline

Date: 2026-09-13. Branch: `v3/design`. Starting production revision:
`37fc810f1267dd0e692a94764c8710f39d3c59a8`.

The owner approved `docs/RELAY_EXPERIENCE_PLAN.md`, with execution restricted to
experience Stages 0 and 1. The authoritative plan now references that phase while
preserving the completed original V3 stages. No Stage 2 or later work is authorized.
The first sequence is HOME, F7, END, PAUSE, PGUP, CAPSLOCK, ESC, HOME; INSERT is a
fallback only if physical testing demonstrates Pause is absent.

Actual fresh baseline command: `.venv/bin/python -m pytest -q`.
Result: **1,321 passed in 35.30 seconds**. All existing tests passed without changes.
`tests/conftest.py` retains the audit hook blocking shell execution and real machine
executables. No real logout, reboot, shutdown or terminal-closing action was run.

Environment observed at this baseline:

| Item | Actual value |
| --- | --- |
| OS | Arch Linux, kernel `7.1.9-arch1-2`, x86_64, glibc 2.44 |
| Python | 3.14.7 |
| cryptography / pytest | 50.0.1 / 9.1.1 |
| Session | Wayland, Hyprland 0.56.2 (`efb50993780079460b0cbed1363e2166a2de1d9f`) |
| Display endpoints | `WAYLAND_DISPLAY=wayland-1`, `DISPLAY=:0` |
| Installed viewer | `/usr/bin/imv`, 5.0.1 (not replaced) |
| Available terminal | `/usr/bin/foot` (not launched by tests) |
| C compiler | GCC 16.2.1 |
| Libraries via pkg-config | wayland-client 1.26.0, wayland-egl 18.1.0, xkbcommon 1.13.2, libpng 1.6.58, pangocairo 1.58.2, EGL 1.5, GL 1.2 |
| Missing build/test tools on PATH | meson, ninja, weston, sway, Xvfb, wayland-info |
| Other available tool | wtype; synthetic input would not establish physical keyboard support |

The presence of `DISPLAY` does not qualify X11 or XWayland. Stage 0 changed only
planning/verification documents. The production cryptography/storage code is intact.
Stage 0 is separately reviewable in commit `ca9e0fc`.

## Stage 1 — isolated imv feasibility gate

The probe, reproducible build, tests and owner instructions are under
[`integrations/imv/`](../../integrations/imv/README.md). No system package, file
association, user desktop configuration, Relay preferences or production module
was changed. No Relay terminal experience was launched. Only disposable PNGs and
viewer processes were used. All viewer children created for the probe were stopped.

### Upstream correction and exact patch

The planning document cited GitHub revision `2144bea...`; inspection of its README
and commit date established that it is the archived 2021 repository. The active
upstream is `https://git.sr.ht/~exec64/imv`. Stage 1 instead pins **v5.0.1** at
`bdec0e527be289e08c3a70c8719a85994d26bd4d`, matching the installed viewer's release.
This correction does not change the approved viewer strategy or touch the core.

The final patch is **293 added / 18 removed lines across seven upstream files**:

| File | Added / removed | Purpose |
| --- | --- | --- |
| `src/backend_libpng.c` | 22 / 4 | Stamp the actual descriptor before header reads; verify after pixel decode |
| `src/image.c` | 14 / 0 | Carry immutable origin with the decoded image |
| `src/image.h` | 14 / 0 | Origin data and full stat-identity comparison |
| `src/imv.c` | 95 / 1 | Observe renderer state, require coherent submitted geometry, report eligibility, reset partial state |
| `src/relay_probe.h` | 104 / 0 | Bounded fixed-sequence matcher and eligibility/invalidation predicate |
| `src/window.h` | 4 / 0 | Separate focus and raw-key event types |
| `src/wl_window.c` | 40 / 13 | Surface focus, held-key tracking and initial/release/repeat events; guard repeat timer setup |

Build profile: native Wayland, libpng only, C11, GCC 16.2.1, meson 1.12.0 and ninja
1.13.2 in an isolated `/tmp` virtual environment. Build tools were not added to
Relay's dependencies. A fresh checkout reproduced the final patch/build; all seven
patched source files matched byte-for-byte. The final build emitted no warnings.

### Actual tests and observations

The full existing suite was run again during Stage 1:
**1,321 passed in 50.00 seconds**. Production tests/code and the OS-action audit
guard are unchanged. No real logout/reboot/shutdown/terminal-closing action was
executed. Test cleanup terminated only the disposable imv processes we created.

Two isolated C test programs passed against the patched build and the fresh
reproduction. They cover the exact geometry and pose-invalidation functions used
by the viewer, timeout/prefix/overlap/press classification, and the real libpng
decoder's descriptor identity before and after replacement and during-load mutation.
Their synthetic key events/seeded prefixes are explicitly **not physical-key evidence**.

The final actual Wayland run passed **12 checks**, without synthesized keyboard
input or compositor/window polling. Its state evidence is retained in
[`wayland.json`](../../integrations/imv/evidence/wayland.json).

| Observation | Actual result |
| --- | --- |
| Viewer identity | Instrumented imv reports its fixed development identity and own PID; no title matching |
| Native Wayland focus | Enter, leave to a second disposable viewer, and reenter observed |
| Exact selected and displayed paths | Both read inside imv; reported as escaped hex paths; correct target accepted and other image rejected |
| File/load identity | Stable descriptor-derived generation observed; no relabeling of displayed pixels from a new path stat |
| Zoom | Actual scale 1 accepted for 0.9–1.1 interval; approximately 3.2434 rejected |
| Pan / target viewport | Centered 100×100 region accepted; 500-pixel pan rejected |
| Image dimensions | Actual fixture 800×600 |
| Window / framebuffer | Settled 875×600 logical / 1750×1200 framebuffer; fullscreen resize 1280×720 / 2560×1440 |
| Rotation / mirror | 90-degree rotation and horizontal mirror observed and rejected |
| Image changes | Navigation changed load generation and rejected the other path |
| Replacement | Same-mtime atomic replacement kept old displayed inode but immediately made the probe ineligible on its next observation |
| Explicit reload | Navigating away/back decoded the new inode and restored file-identity eligibility; zoom predicate remains independent |

An early probe exposed mixed resize/render dimensions. The final patch fails closed
while draw/resize state is pending, waits for the viewer's submitted frame, and
invalidates the prefix across that boundary. This establishes the viewer's own
submitted rendering state, not exact compositor scanout time or an atomic desktop
launch transaction. There is no launcher in Stage 1.

Partial sequence invalidation is tested for **focus, zoom, pan, resize, image
generation and file identity** through the same pose-update function used by the
real viewer. Actual compositor/viewer tests establish those changing observations.
The combined physical-key-plus-interruption journey remains unverified.

### Requested physical keys — incomplete qualification

A native Wayland development window was opened and a request for the owner to
physically press the requested keys was presented. It received **no named test-key
events**, and no completed physical-test response arrived before this gate report.
The window was then stopped; no background listener remains. Aggregate evidence is
in [`physical-keys.json`](../../integrations/imv/evidence/physical-keys.json).

| Requested key | Release / initial press / repeat received | Qualification |
| --- | --- | --- |
| HOME | 0 / 0 / 0 | Unverified |
| F7 | 0 / 0 / 0 | Unverified |
| END | 0 / 0 / 0 | Unverified |
| PAUSE | 0 / 0 / 0 | Unverified |
| PGUP | 0 / 0 / 0 | Unverified |
| CAPSLOCK | 0 / 0 / 0 | Unverified |
| ESC | 0 / 0 / 0 | Unverified |
| INSERT | 0 / 0 / 0 | Unverified |

These zeros do **not** mean the keyboard lacks those keys. Its model and physical
Pause behavior have not been established. Do not recommend/activate the Insert
fallback on this evidence. Physical initial/release/repeat behavior, Caps Lock
effects, held keys across focus changes and the full preferred sequence must still
be exercised with the final probe. No global capture or `/dev/input` fallback was
attempted, and no synthetic event was misrepresented as a physical key.

### Qualification and unresolved risks

* **Native Wayland / Hyprland 0.56.2:** real focus, file and geometry observations
  passed on the current 2× display configuration. Overall doorway qualification is
  incomplete because physical input was not established.
* **X11:** not built or tested; not qualified.
* **XWayland:** not tested; not qualified. `DISPLAY=:0` proves nothing about support.
* **Reload behavior:** upstream checks second-resolution mtime and misses some
  same-timestamp replacements. The observer correctly rejects stale displayed data.
  Explicit reload works; automatic reload improvements would need a separate small
  design decision, not permission to relax identity checks.
* **Backend scope:** libpng only; relative/aliased paths, other decoders, multi-seat
  or keymap replacement, fractional scaling and rapid repeat/focus/teardown need
  further qualification. There is no universal keyboard claim.
* **Threat boundary:** same-user/root tampering, X11 injection and exact display
  scanout remain outside concealment guarantees. Password/core encryption remain
  the actual protection. No cryptographic incompatibility was identified.
* **Production readiness:** the probe intentionally exposes development diagnostics,
  reserves its test keys and uses only a fixed sequence. It is not a finished input
  subsystem or installed integration. No Stage 2 or later work was performed.

The small imv strategy remains technically plausible; the available evidence does
not force a different viewer. However, the owner's required physical-key gate is
not satisfied. A subsequent authorized attempt must close that evidence gap and
review the reload/input limitations before treating Stage 1 as passed.

**STAGE 1 DOES NOT PASS — revise viewer strategy before continuing**
