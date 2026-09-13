# Super Secret Vault V3

This specification implements the accepted V3 design. The old plan in
`docs/history/V1_IMPLEMENTATION_PLAN.md` is reference only.

## Product and boundaries

Relay is a local encrypted vault concealed inside an ordinary PNG, reached through
COVER → WAKING → ROUTE → AUTHENTICATING → UNLOCKED. Wake and route are theater,
never authentication. Linux first, small personal vaults, direct password
maintenance access, automatic backups, separately armed optional OS actions.
Python 3.12+, cryptography and standard library; no database, daemon, plugin
framework, shell execution, compression or network features.
Package relayvault; distribution super-secret-vault; executable relay. One-release
`python -m vaultgame` shim. RELAY_HOME precedes VAULTGAME_HOME; default ~/.relayvault.

## Portable data

One versioned capsule with public crypto header, encrypted schema-2 manifest,
RVLT v1 encrypted objects and completeness footer. Standalone .relayvault or
PNG private rvLt chunks. Legacy directories are read-only migration sources.
Keep Argon2id (16-byte salt, 65536 KiB, 3 iterations, 4 lanes, 32-byte key),
AES-256-GCM (fresh random 12-byte nonces, full tags), existing AAD and key check.
Manifest authenticates header digest, snapshot ID/generation, object ranges and
ciphertext hashes. No plaintext names outside encrypted metadata. No plaintext
publication until authentication and size validation; no overwrite on retrieval.
Verification discards decrypted bytes without plaintext disk files. Idle lock
300 seconds, serialized operations, best-effort key wiping only.
Validated operational envelope: recommend <=100 MiB for frequent writes; near
1 GiB, full commits measured 48–78 seconds. Keep the supported hard limit. PNG
covers are capped at 128 MiB to bound parser resources.
Limits: 1 GiB capsule, 64 KiB header, 16 MiB manifest, 10000 entries, 1 MiB PNG
segments. Bound untrusted allocation, reject duplicates/overlaps/missing records,
unsupported versions and trailing data. Byte layout is frozen in docs/FORMAT.md.

PNG creation preserves original image chunks, inserts numbered private chunks
before IEND and always writes a new destination. Reject APNG and existing
carriers. Reassembly does not depend on adjacency. Capsule validity does not
require image validity during recovery. PNG rewrites may strip all payload;
no guaranteed photo-service survival, undetectability or fragment salvage.

## Transactions, migration and recovery

Stable exclusive local locks by canonical path and vault identity. Fully verify
source; durable encrypted backup outside Pictures; private sibling staging;
fully verify replacement; fsync; source-change check; atomic publication;
parent-directory fsync; acknowledge; prune to three previous states. Initial
creation also has a backup. Fail closed on backup failure/disk full/unsafe paths.
Post-publication sync failure is explicitly uncertain, never reported rolled back.
Only owner-controlled local Linux filesystems support writes; no concurrent
noncooperating editor or cloud conflict guarantees.

Migrate V1/V2 by authenticating all referenced objects, preserving crypto identity,
password and ciphertext, writing schema 2 to a new target, verifying and rechecking
source. Never mutate source; report orphans. Missing cooldown state is acceptable.
Explicit verify/backup/export/recover; recover to new path, never silent rollback.
Carrier plus password suffices on compatible Relay; local policy is optional.
Copies diverge independently. No password recovery, rollback prevention, secure
erasure or automatic merging claims. Backups retain deleted files.

## Interaction and policy

Cover: alternate screen, neutral Relay/system/file information, no prompt/help,
vault/cipher/object information or echo. Non-TTY prints static diagnostics and
exits. One TTY input owner handles key decoding, line editing, bracketed paste,
resize and restoration. Default wake r e l a y UP UP DOWN LEFT RIGHT, prefix-aware,
5-second idle reset. Errors invisible. Ignore pasted wake; drain input at state
boundaries; waking under 400 ms. Paste does not submit; require separate Enter.
Echo remains disabled with effects off. No persistent input history. Timeout
redraw within 100 ms; restore on Ctrl+C/EOF/hangup/errors/suspend/resume.
Route is `attach 13`, `unlock`; no discovery prerequisite. Optional fixed status,
ls/cat, diagnostics/back/sleep/exit. No shell or host filesystem in route.
CLI: open; init [--image]; maintenance; migrate [--image]; export [--image];
verify; backup; recover; configure. Passwords never in arguments. Existing
list/store/retrieve/remove/rename/info/lock/clear/help/exit vault commands remain.
Wake/default target/effects/idle and OS policy are local. Three auth failures:
30-second local backoff, independently of effects; not offline protection.
Incidents describe link reset, not fake data corruption. Fixed OS actions require
local enabled flag, binding, allowlist AND --arm-os-actions per launch. Never
inherit activation from a carrier/migration or trigger from dormant input, auth
failure, maintenance or storage failure. Lock/finish I/O before real actions.
All automated tests must block real process execution by the action executor.

## Ordered stages and tests

0. Safe passing baseline; archive old plan; update instructions.
1. PNG/streaming/PTY prototypes; two independent decoders, pixels, 1/100/1024 MiB
   payloads, write-cost measurements; freeze format. Document envelope revisions.
2. Rename and local/portable boundaries; crypto regression, entrypoints, parser.
3. Standalone codec/session; malformed framing, crypto identity, large streams,
   fresh nonces and authenticated non-overwriting publication.
4. Durable commit/backup/recovery; write/sync/publish failure injection, concurrency,
   external edit, disk-full and killed disposable writer.
5. PNG/migration/export; pixel equivalence, stripping/reordering/truncation, image
   damage with intact capsule, source preservation and fresh-home portability.
6. Dormant input and route; PTY echo/fragment/paste/timeout/resize/restore checks.
7. Incidents, docs, installed-package journeys, full suite and identity audit.

Run relevant tests and fix failures before proceeding to the next stage.

## Definition of completion

All stages working, no required placeholders. Full suite and installed-package
checks pass. Declared independent PNG decoders preserve pixels. Carrier/password
works in fresh home. Legacy migration, round trips, explicit backup recovery and
interrupted commits verified. No failed authentication publishes plaintext. Tests
never log out/reboot/shut down/close terminal. Documentation states limitations.

## Implementation completion record

Stages 0–7 are implemented. Final verification: 1321 passing tests and a rebuilt
wheel exercised in a fresh environment outside the checkout. See
`docs/verification/RELEASE.md` for stage evidence, operational limits and measured
carrier performance. No real machine action was executed during verification.
