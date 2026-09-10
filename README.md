# Super Secret Vault

A local encrypted file vault behind a sparse, internal relay interface. This branch contains the **experimental V2 terminal overhaul**; the stable V1 history and original `IMPLEMENTATION_PLAN.md` remain intact.

Requires Python 3.12 or newer. Install from this checkout:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install .
relay init
relay
```

`relay init` asks for a password twice and refuses to overwrite existing vault data. Normal startup never initializes automatically. `python -m vaultgame` and `python -m vaultgame init` provide the same entry points.

Data lives in `~/.relayvault/`. Set `VAULTGAME_HOME` to use another location. Back up the **entire directory**, including `config.json`, `state.json`, and `vault/`, while the application is closed. Keep the backup private. Losing the password means losing access: there is no password recovery.

After unlocking, use `help` for `list`, `store`, `retrieve`, `remove`, `rename`, `info`, `lock`, `clear`, and `exit`. Quote paths or names containing spaces. Removal requires `y` or `yes` (case-insensitive); any other answer cancels. Retrieval refuses an existing destination. **Retrieved plaintext copies are outside the vault's protection.** Storing a file also leaves its original source untouched.

`lock` returns to `relay_root`, discarding all navigation state. Idle sessions lock after the configured `auto_lock_seconds` (300 seconds by default). If input is waiting when a timeout occurs, the next entered command is ignored and the relay restarts. `exit`, Ctrl+C, and EOF close the session and restore the terminal. Key-buffer cleanup is best effort; guaranteed memory erasure is not possible in Python.

Destructive-looking relay effects are fictional and do not delete or corrupt vault files. Some traps impose a cooldown that survives restart. Effects become readable static output when stdout is not a terminal or when presentation effects are disabled.

**Real OS trap actions can log you out, reboot, shut down, or attempt to close a supported terminal. Leave them disabled unless you deliberately accept those consequences.** They are disabled by default, with no allowlisted actions and no bindings. Dispatch requires all three: `real_os_actions.enabled`, an explicit trap binding to a supported symbolic action, and that action in `allowed_actions`. Platform support is limited; unsupported actions fail through a controlled error. Never enable real actions for automated tests.

Install development dependencies and run the tests:

```sh
python -m pip install '.[dev]'
python -m pytest
```

Tests use disposable temporary vaults and mock real OS actions. Do not use personal files for development checks.

## Experimental V2

Startup displays a brief bootstrap and a vault schematic beside public diagnostics (stacked on narrow terminals), with the first prompt directly below. Object counts include only regular opaque objects on disk, including any unreferenced objects; the dashboard never decrypts the manifest or displays protected filenames. Relay and carrier fields describe fictional interfaces, not network connections.

Ten environments replace V1's five puzzle areas: seven on the route to authentication, plus diagnostics, a white archive, and red maintenance. Inspect the local interface with `ls`, `cat`, `status`, and `pwd`; `help` lists command vocabulary without route arguments. Every pseudo-resource is explicitly defined. These commands are **not a shell**, do not browse the host filesystem, and cannot execute programs. Navigation state never persists, and each launch requires the route again. The learned route has eleven commands, designed for roughly 20–40 seconds of typing with routine effects skipped.

Routine transitions preserve terminal history. Cyan accents and short synchronization indicators accompany navigation; press a key to skip a routine effect. The skip key (including pending escape-sequence bytes) is consumed, and the original input mode is restored. Bootstrap and successful authentication each use a fixed 1.2-second sequence. `store` and `retrieve` show brief completion effects after the real operation succeeds; their bars are cosmetic, not byte-level transfer meters. Other vault commands remain immediate. Explicit `clear`, session locking, and a few incident effects can still clear the display.

Maintenance writes can cause a simulated journal incident and disconnect. Wrong controller operations and repeated authentication failures retain V1's persisted backoff policy; the interface reports the remaining timer and exits without making the user watch it count down. All cryptography, encrypted formats, password handling, storage semantics, idle locking, and real OS-action gates are unchanged. No dependencies, network features, database, or plugins were added.

The V2 tests include real pseudo-terminal input-mode checks on POSIX, injected animation timing, all environments, dashboard confidentiality, and complete encrypted-vault journeys. From the activated development environment, run `python -m pytest`; an existing checkout environment can also be used as `.venv/bin/python -m pytest`.
