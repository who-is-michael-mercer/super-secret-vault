# Baseline and feasibility

V2 f6a7afc: 927 tests passed (Python 3.14.7, cryptography 50.0.1).
The unmodified-behavior reference implementation and its tests live exclusively
under tests/v2_reference and tests/legacy. They are not installed. Production
crypto/parser/rendering/OS-action regressions also run against relayvault.

Disposable carrier probe (scripts/prototypes/carrier_probe.py), this machine:

| Payload | Write + fsync | ImageMagick | FFmpeg |
| --- | --- | --- | --- |
| 1 MiB | 0.004s | 0.021s | 0.202s |
| 100 MiB | 0.460s | 0.231s | 0.221s |
| 1 GiB | 4.649s | 2.122s | 0.986s |

Both independent decoder families emitted identical RGB bytes at every size.
These are sequential-write measurements, not complete encrypted commit timings
or guarantees for other filesystems. The 1 GiB capsule limit remains appropriate.
Existing POSIX terminal regression/prototype coverage: 78 tests passed.

## Complete production snapshot commits

`scripts/prototypes/snapshot_probe.py` creates disposable PNG carriers and runs
actual encryption, all verification, backup, staging, replacement and syncing.

| File payload | Store | Rename with backup |
| --- | --- | --- |
| 1 MiB | 0.074s | 0.104s |
| 100 MiB | 6.005s | 8.457s |
| 1023 MiB | 48.265s | 78.393s |

The hard capsule limit remains 1 GiB; **100 MiB or smaller is the recommended
routine-write envelope**. Near-limit updates are bulk operations and can take over
one minute. No weaker verification, journaling or format change was substituted.
PNG covers are bounded at 128 MiB to bound framing/metadata resource use.

The fixed capsule fixture in tests/fixtures/capsule-v1.json was encoded separately
using cryptography's AESGCM and Argon2id and explicit struct framing, not Relay's
writer. Its credentials and nonces are test-only known-answer values.

Installed-wheel smoke: fresh virtual environment, outside checkout, no PYTHONPATH;
PNG init, dormant wake, two-command route, authentication, verification, relay
executable and python -m vaultgame all passed. Reproduce with:

```sh
.venv/bin/python -m pip wheel --no-deps . -w dist
.venv/bin/python scripts/verify_wheel.py
```
