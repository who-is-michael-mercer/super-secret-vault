# Super Secret Vault

A local encrypted file vault reached through a mysterious terminal game. Explore the relay and its clues; the protected file commands become available after authentication.

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

`lock` returns to the beginning of the game. Idle sessions lock after the configured `auto_lock_seconds` (300 seconds by default). If input is waiting when a timeout occurs, the next entered command is ignored and the relay restarts. `exit`, Ctrl+C, and EOF close the session and restore the terminal. Key-buffer cleanup is best effort; guaranteed memory erasure is not possible in Python.

Destructive-looking game effects are fictional and do not delete or corrupt vault files. Some traps impose a cooldown that survives restart. Effects become readable static output when stdout is not a terminal.

**Real OS trap actions can log you out, reboot, shut down, or attempt to close a supported terminal. Leave them disabled unless you deliberately accept those consequences.** They are disabled by default, with no allowlisted actions and no bindings. Dispatch requires all three: `real_os_actions.enabled`, an explicit trap binding to a supported symbolic action, and that action in `allowed_actions`. Platform support is limited; unsupported actions fail through a controlled error. Never enable real actions for automated tests.

Install development dependencies and run the tests:

```sh
python -m pip install '.[dev]'
python -m pytest
```

Tests use disposable temporary vaults and mock real OS actions. Do not use personal files for development checks.
