# Super Secret Vault — Relay V3

A local encrypted vault concealed behind a dormant terminal interface. An ordinary
PNG can carry the encrypted vault and still display its original picture.
The private access procedure is the door. Your password and encryption are the lock.

Linux, Python 3.12 or newer. Install and run from this checkout:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install '.[dev]'
relay init ~/Pictures/quiet.png --image ~/Pictures/original.png
relay open ~/Pictures/quiet.png
```

Use a static PNG as the source. Creation writes a new file and never overwrites
an existing image. JPEG conversion, animated PNGs and other carrier formats are
not supported. The carrier is a complete, portable vault; no sidecar is needed.

The initial screen has no prompt. Type the default wake sequence without Enter:

**r e l a y ↑ ↑ ↓ ← →**

At the revealed prompt, enter `attach 13`, then `unlock`. Enter your actual vault
password at the password prompt. The learned route has two commands. Optional
`ls`, `cat interfaces`, `status` and `attach diagnostics` inspect fixed fictional
resources; this interface cannot execute shell commands or browse your machine.
`back`, `sleep` and `exit` return, sleep or disconnect. `reset channel` invokes a
fictional incident and can invoke a separately armed local machine action.

After unlocking, `help` lists:

| Command | Purpose |
| --- | --- |
| `list` | List protected files |
| `store "<source>" [name]` | Encrypt a file; leave the original source untouched |
| `retrieve <name> "<destination>"` | Authenticate and write a new plaintext copy |
| `remove <name>` | Remove after confirmation |
| `rename <old> <new>` | Rename a protected file |
| `info <name>` | Display protected metadata |
| `lock` | Drop the session and return to dormant cover |
| `clear`, `help`, `exit` | Clear, inspect commands, or lock and exit |

Quote names and paths containing spaces. Retrieval refuses existing destinations,
symlinks and Relay's private state directory. Retrieved copies and original source
files are outside vault encryption. Removal does not securely erase backups.

## Owner configuration and maintenance

```sh
relay configure --target ~/Pictures/quiet.png
relay configure --wake r e l a y UP UP DOWN LEFT RIGHT
relay configure --reset-wake
relay configure --effects off --idle 300
relay maintenance ~/Pictures/quiet.png
```

A configured target lets `relay` start its cover directly. Wake, effects, idle
settings and OS permissions are local, in `~/.relayvault/preferences.json`.
`RELAY_HOME` overrides that directory; `VAULTGAME_HOME` is a deprecated fallback.
`python -m relayvault` and, for one release, `python -m vaultgame` also work.

Maintenance skips the private procedure and asks directly for the password.
The wake sequence is not authentication and can be reset without the password.
If local preferences are damaged, select a fresh `RELAY_HOME` for recovery.
Three failed authentication attempts cause a local 30-second backoff, including
maintenance. This does not constrain offline password guessing.

Password operations require a real terminal and never take passwords through
arguments or redirected input. Pasted text requires a separate Enter. Password
paste preserves exact text, including any clipboard newline or tab. Passwords
are never echoed. Effects-off mode also keeps input echo disabled. Normal startup
with redirected output prints only static cover information and exits.

Sessions lock after 300 seconds idle by default and clear the visible vault screen
without waiting for another key. Active storage operations finish before idle
locking. Ctrl+C, EOF or terminal loss closes the session. Suspend restores terminal
settings; resuming returns an interactive session to cover. Python cannot guarantee
complete removal of secrets from RAM, swap or external terminal recording.

## Portability, backups and recovery

Copy the **complete file**, byte for byte, to another Linux machine with compatible
Relay. The file and password suffice; a fresh installation uses the default wake
sequence, and maintenance always reaches password authentication directly.

Photo editors, optimizers and cloud photo services may discard private PNG chunks.
Use file-copy/original-file transfer, not image export, screenshot, resizing or
photo-sharing transformations. A stripped carrier can become an ordinary PNG with
no way to prove from that image alone that it once contained a vault. File size
and binary inspection can reveal the payload; this is not forensic concealment.

Each mutation first verifies and backs up the existing encrypted snapshot under:

```text
~/.relayvault/backups/<hashed-vault-identity>/<generation>-<snapshot-id>.relayvault
```

Relay keeps three previous encrypted states and saves an initial recovery copy.
Backups require the same password and contain no machine-action policy. A local
backup does not protect against disk loss. Make another copy on a separate device:

```sh
relay backup ~/Pictures/quiet.png /media/backup/quiet.relayvault
relay verify /media/backup/quiet.relayvault
relay export ~/Pictures/quiet.png ~/Documents/conventional.relayvault
relay export ~/Documents/conventional.relayvault ~/Pictures/repacked.png --image ~/Pictures/original.png
relay recover /path/to/selected-backup.relayvault ~/Documents/recovered.relayvault
```

Recover authenticates the selected snapshot, shows its generation/time and asks
before writing a new destination. It never repairs the source in place or silently
chooses an older state. To recover an intact capsule from a PNG with damaged image
checksums, use that PNG as the recovery source. Missing payload bytes, broken PNG
framing or damaged cryptographic metadata may require an independent backup;
there is no arbitrary fragment salvage or password recovery.

Exports preserve the exact capsule bytes. Copies evolve independently, without
merging or synchronization. Generation numbers do not prevent replacement with
an older valid copy. Deletions remain recoverable from retained backups.

## Existing V1/V2 vaults

Close V1/V2 and retain a complete backup of its directory. Relay state must be
outside the legacy source so migration cannot add even backup/lock files to it.
For a vault in the default application directory, use
`RELAY_HOME=~/.relayvault-v3 relay migrate ~/.relayvault <destination>` and keep
that new `RELAY_HOME` for subsequent V3 commands. For a separate source directory:

```sh
relay migrate /path/to/old/.relayvault ~/Documents/migrated.relayvault
relay migrate /path/to/old/.relayvault ~/Pictures/migrated.png --image ~/Pictures/original.png
```

Migration verifies every referenced object and the new output, preserves the old
password/identity/ciphertext, and leaves all source files untouched. Missing
cooldown state is acceptable. Orphans are counted and retained. OS-action
activation and presentation settings are never imported.

## Storage and safety boundaries

Argon2id uses the existing 64 MiB / three-iteration / four-lane profile. AES-256-GCM
records retain fresh random nonces, full authentication tags and identity-bound
AAD. Names and logical metadata are encrypted. Public framing and PNG CRCs are
damage checks, not cryptographic authentication. See [the format](docs/FORMAT.md).

The supported envelope is a **1 GiB capsule, 10,000 files, and a static PNG cover
up to 128 MiB**. Writes stream bounded chunks but rebuild the entire snapshot and
carrier. Allow several times the vault size in free space for backups and staging.
For frequent updates, keep the capsule around **100 MiB or smaller**. Measured
near-limit writes took 48–78 seconds on the development machine; even rename
rewrites and verifies the complete snapshot. See the measured results in
[verification notes](docs/verification/BASELINE.md). Relay does not compress files.

Updates require mandatory backup, complete staging validation, file fsync, atomic
replacement and parent-directory fsync. Stable locks reject concurrent Relay
sessions for a vault; changed sources refuse mutation. Writes require owned files
without symlink/hard-link aliases on a local Linux filesystem. Do not concurrently
edit the image, run the old vault writer or rely on cloud conflict resolution.
Network/removable filesystems that lack the required operations are unsupported.

If syncing fails after publication, Relay reports **durability uncertain**, closes
the writable session and requires verification. It does not claim the old state
was restored. Process interruption can leave encrypted `.relay-*.partial` staging
files; after closing Relay, these may be removed. Interrupted retrieval can leave
a private plaintext `.partial` in the selected retrieval directory; inspect and
remove it as sensitive data. Live errors clean up their staging files.

Optional real OS actions remain disabled by default. Enabling requires editing the
local `real_os_actions` section with `enabled: true`, an explicit `channel_reset`
binding and an allowlist, plus `relay --arm-os-actions open <carrier>` for that
launch. Supported fixed actions are logout, reboot, shutdown and closing an
identified local Kitty window. Only the explicit route incident can trigger them;
never cover input, authentication failure, maintenance or storage errors. They can
interrupt your desktop session. Automated tests must never execute them.

## Development and verification

```sh
.venv/bin/python -m pytest -q
```

Tests use disposable vaults and block real machine-action execution. Historical V2
reference code lives only under `tests/v2_reference`; it is not installed. Its
compatibility suite remains under `tests/legacy`. V3 regressions directly exercise
production crypto, codec, commits, migration, PNG and real pseudo-terminal CLI.
The implementation stages are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
Measured decoder compatibility and release checks are in
[docs/verification](docs/verification/BASELINE.md).
