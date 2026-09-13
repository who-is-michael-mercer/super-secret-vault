# V3 implementation verification

Final verification on 2026-09-12:

- Python 3.14.7, cryptography 50.0.1, pytest 9.1.1, Linux.
- **1321 tests passed** in 37.45 seconds: 927 historical V2 compatibility tests
  plus 394 tests against V3 production behavior and preserved primitives.
- The rebuilt super_secret_vault-3.0.0 wheel passed a fresh-venv PTY smoke test
  outside the checkout without PYTHONPATH: PNG initialization, dormant wake,
  attach/unlock route, password authentication, verification, relay executable
  and deprecated module shim.
- Wheel contains neither the V2 reference implementation nor tests; vaultgame
  contains only its module forwarding shim.
- ImageMagick and FFmpeg independently decoded unchanged original pixels from
  production carriers. Larger transport and full encrypted-commit measurements
  are recorded in BASELINE.md.
- git diff --check and Python bytecode compilation passed.
- No real logout, shutdown, reboot or terminal-closing action was executed.
  Tests use recording executors and an audit hook rejecting machine executables.

## Stage completion

| Stage | Evidence |
| --- | --- |
| 0 — baseline/specification | Original plan archived, V3 instructions active, 927 baseline tests preserved |
| 1 — feasibility/format | 1/100/1024 MiB PNG probes; two decoders; PTYs; exact FORMAT.md and independent known-answer fixture |
| 2 — identity/boundaries | relayvault package, forwarding shim, separate local settings, preserved primitive regressions |
| 3 — capsules | Bounded streaming, authenticated header/object bindings, wrong-password and malformed-frame tests |
| 4 — durable writes | Backup/ancestor syncing, exclusive locks, injected disk/write/sync/replace failures; disposable process interruption before and after publication |
| 5 — carriers/migration | PNG chunk preservation/reordering/stripping/corruption, intact-capsule recovery, fresh-home round trips, read-only V2 migration |
| 6 — dormant interface | Hidden echo-free wake, two commands, paste and fragmented input, buffer boundaries, immediate timeout, suspend/resume and signal restoration |
| 7 — release | Gated incidents, owner docs, full suite, installed wheel and language audit |

## Operational decisions verified during implementation

- Keep the 1 GiB hard capsule ceiling, but recommend <=100 MiB for frequent
  updates. Whole-snapshot operations near the ceiling measured 48–78 seconds.
- Bound ordinary PNG cover data at 128 MiB. No image conversion is performed.
- Require RELAY_HOME outside a legacy migration source; even lock/backup files
  must not be added to the source directory during migration.
- Export preserves exact capsule bytes; it does not manufacture a new generation.
- Password paste preserves exact text, including newline/tab; a separate Enter
  submits it. Wrong wake input never echoes.
- Photo transformations can strip the complete payload. Recovery then requires
  an independent snapshot. Generation numbers do not prevent whole-file rollback.
- Crash-interrupted encrypted staging files can remain. Interrupted retrieval can
  leave a mode-0600 plaintext partial at the requested destination; the README
  documents cleanup and the existing Python memory-erasure limitations.

This is implementation and regression evidence, not a claim of an independent
security audit or of guarantees on untested filesystem/platform combinations.
