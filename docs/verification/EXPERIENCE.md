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
Stage 1 evidence will be recorded separately below after actual probe work.
