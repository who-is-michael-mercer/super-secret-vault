# Super Secret Vault — Relay V3

An ordinary PNG carries a personal encrypted vault. The supported Swayimg opens
that picture normally; a particular image pose and physical key sequence open a
quiet file inspector. Two hidden terminal sequences construct a large ASCII vault,
then dissolve it into a small fictional terminal route.

Image pose, sequences and the route are **concealment only**. Password authentication
and encryption protect the actual vault. No global input capture or Relay daemon.
The visual door targets **Arch Linux / Hyprland / native Wayland / patched Swayimg**;
Foot is the qualified terminal. Maintenance works independently of the ritual.

## Try the ready-to-run demo

```sh
.venv/bin/python scripts/experience_demo.py
```

Public disposable-demo password: **13001300**. The demo uses its own local home and
carrier under `.local/demo/`; keep real private material out of it. Follow the
[complete walkthrough](docs/EXPERIENCE_GUIDE.md) for every key sequence, file
operations, tuning, maintenance, setup and feedback targets.

## Install and open an image

Python 3.12+ and the build libraries listed in
[the Swayimg setup guide](integrations/swayimg/README.md) are required. From this checkout:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]' meson==1.12.0 ninja==1.13.2
PATH="$PWD/.venv/bin:$PATH" python integrations/swayimg/build.py .local/swayimg
relay init ~/Pictures/quiet.png --image ~/Pictures/original.png
relay door enroll ~/Pictures/quiet.png
relay view --viewer "$PWD/.local/swayimg/build/swayimg"
```

Reuse `.local/swayimg` if already built; the build script requires a new destination.
Nothing replaces the system viewer, adds file associations, installs a service, or
requires root. Use a static PNG. Creation never overwrites an existing file. The
carrier remains a complete, portable vault without a required sidecar.

## The entrance

1. In Swayimg, press `1` for 100% scale. Default enrollment targets the central
   10% rectangle, near the center of the window, at 90–110% scale. `h j k l` pan;
   `z`/`x` zoom; `r` resets the view; `o` reloads; `q` closes the viewer.
2. Tap and release **Home → F7 → End → PrtSc → PgUp → Caps Lock → Esc → Home**.
   A wrong pose or sequence does nothing. Bare PrtSc must reach Swayimg; screenshots
   on the qualified owner machine already use **Shift+PrtSc**. Caps Lock still toggles.
3. The inspector has no prompt. Enter **Home → F8 → PgUp → End**, without Enter.
4. Let the vault assemble. At the silent completed vault, enter
   **Left → Right → F7 → Home**, without Enter.
5. After it dissolves, enter `peel`, then `follow 3`, then `open`, each with Enter.
6. The screen changes to **LOCAL VAULT / Password authentication required**.
   Enter the real password. This is the authentication boundary.

The route's `ls`, `cat layers`, `inspect 3`, `trace`, `probe`, `status`,
`follow service`, `back` and `knock` inspect only fixed fictional resources.
They cannot execute shell commands, inspect the environment or browse your files.
`peel` is optional once the route is memorized. `sleep` returns to inspection;
`exit` disconnects. `reset channel` retains the existing separately gated incident
policy; the image-door launch never arms real machine actions.

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
relay configure --inspector-sequence KEY_HOME KEY_F8 KEY_PGUP KEY_END
relay configure --vault-sequence KEY_LEFT KEY_RIGHT KEY_F7 KEY_HOME
relay configure --animation-speed fast
relay configure --presentation text
relay door disable
relay configure --effects off --idle 300
relay maintenance ~/Pictures/quiet.png
```

A configured target lets `relay` start its inspector directly. `relay open IMAGE`
is also a deliberate way to test the terminal ritual without the visual door.
Presentation, enrollment, sequences, effects, idle settings and OS permissions are
local, in `~/.relayvault/preferences.json` (private settings version 2). Version 1
migrates without enabling the door or changing its OS policy. The old `wake` remains
available through `relay open IMAGE --legacy-wake`; it replaces only the first
terminal sequence. Named terminal sequences reject Caps Lock, Print, Pause and
modifiers because ordinary terminal protocols cannot deliver them reliably.
`RELAY_HOME` overrides that directory; `VAULTGAME_HOME` is a deprecated fallback.
`python -m relayvault` and, for one release, `python -m vaultgame` also work.

Maintenance skips the private procedure and asks directly for the password.
Hidden sequences are not authentication and can be reset without the password.
Enrollment binds ordinary PNG bytes rather than a permanent inode. After storing or
renaming a protected file, the carrier is atomically replaced: reload Swayimg with
`o` before using the visual door again. Rename the carrier or change its ordinary
image bytes only with deliberate re-enrollment. Symlink/hardlink aliases are refused.
Geometry overrides: `relay door enroll IMAGE --region X Y W H --zoom MIN MAX
--tolerance X Y`. Tolerance uses fractions of window size, not exact pixels.
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

Experience verification: **1,474 tests passed**, 179 focused checks, 13 fresh-wheel
checks and the native Swayimg/Foot journey. Detailed evidence and test-driver limits
are in [the stage record](docs/verification/EXPERIENCE_IMPLEMENTATION.md).
