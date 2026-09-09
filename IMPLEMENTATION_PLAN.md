
# Gamified Terminal Encrypted Vault

This plan fixes the architecture and behavior for the implementation pass. There are no alternate designs to choose between later.

The project will be a **single-process Python terminal application** with two deliberately separate domains:

- **Game layer:** terminal presentation, commands, levels, puzzles, traps, state transitions.
    
- **Vault layer:** password-based key derivation, authenticated encryption, encrypted storage, file operations, locking.
    

There will be no server, database, networking, account system, plugin architecture, background service, or cloud dependency.

---

## 1. Fixed technology choices

### Language

**Python 3.12+**

Reasons:

- good cross-platform terminal support;
    
- excellent standard-library filesystem/process support;
    
- easy character animation and timing;
    
- straightforward packaging for a personal project;
    
- mature cryptographic bindings.
    

### Runtime dependency

Only one third-party runtime dependency:

```
cryptography >= 44.0.0
```

`cryptography` has supported Argon2id since version 44 and provides the authenticated-encryption primitives needed here. ([Cryptography](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/?utm_source=chatgpt.com))

### Development dependency

```
pytest
```

Nothing else is necessary.

Do not use Rich, Textual, Click, Typer, curses, SQLAlchemy, keyring services, or a GUI framework.

---

# 2. Project structure

Use exactly this structure:

```
terminal-vault/
```

Do not add `services/`, `repositories/`, `interfaces/`, `controllers/`, `models/`, or similar architectural layers.

---

# 3. Program entry points

`pyproject.toml` should expose one installed command:

```
relay
```

Conceptually:

```
relay
```

`relay` starts the mysterious game.

`relay init` is the explicit administrative first-run setup path.

Do not put vault-creation commands inside the fictional game environment.

`python -m vaultgame` should behave identically to `relay`.

---

# 4. Runtime filesystem layout

Default application data directory:

```
~/.relayvault/
```

Allow a single environment-variable override for tests/development:

```
VAULTGAME_HOME
```

Runtime contents:

```
~/.relayvault/
```

Important properties:

- plaintext filenames do **not** appear in `objects/`;
    
- object filenames are random UUID-derived IDs;
    
- the mapping between object IDs and real filenames exists only inside the encrypted manifest;
    
- no database exists.
    

---

# 5. Persistent data

Only three things persist.

## `config.json`

Plaintext configuration necessary to unlock and operate the vault.

Exact logical shape:

```
schema_version: 1
```

The password itself, password hash, or derived master key is never stored.

## `state.json`

Only runtime state that must survive process exits:

```
schema_version: 1
```

Do **not** persist normal game progress.

Every fresh launch starts at the first game level.

## `manifest.vlt`

Encrypted metadata.

Plaintext representation before encryption:

```
version: 1
```

No directories in version 1.

The vault is deliberately a flat collection of files.

---

# 6. `config.py`

## Responsibility

Own:

- application paths;
    
- JSON config loading;
    
- JSON runtime-state loading;
    
- atomic config/state writing;
    
- defaults;
    
- structural validation.
    

It knows nothing about game levels or encryption operations.

## Main structures

### `AppPaths`

Fields:

- `home`
    
- `config_path`
    
- `state_path`
    
- `vault_dir`
    
- `manifest_path`
    
- `objects_dir`
    

### `AppConfig`

Fields matching `config.json`.

### `RuntimeState`

Fields:

- `cooldown_until`
    

## Functions

Implement:

- `resolve_paths(home_override=None) -> AppPaths`
    
- `load_config(paths) -> AppConfig`
    
- `save_config_atomic(paths, config)`
    
- `load_runtime_state(paths) -> RuntimeState`
    
- `save_runtime_state_atomic(paths, state)`
    
- `is_initialized(paths) -> bool`
    
- `ensure_runtime_directories(paths)`
    
- `validate_config(data) -> AppConfig`
    

Atomic JSON writes should use a temporary file in the same directory followed by replacement.

Malformed config should never silently fall back to defaults.

---

# 7. `terminal.py`

All visual timing belongs here.

No other module should directly call `time.sleep()` for effects.

## Main class

### `Terminal`

Constructor dependencies:

- output stream;
    
- effects enabled/disabled;
    
- sleep function.
    

The injected sleep function allows tests to use a no-op.

## Required methods

- `print(text="", ...)`
    
- `type_text(text, chars_per_second=...)`
    
- `line_delay(milliseconds)`
    
- `clear()`
    
- `hide_cursor()`
    
- `show_cursor()`
    
- `reset_formatting()`
    
- `progress(label, duration, width=...)`
    
- `animate_frames(frames, frame_delay, loops=1)`
    
- `countdown(seconds, prefix=...)`
    
- `fake_system_messages(lines)`
    
- `scramble_text(text, passes=...)`
    
- `flash_lines(lines, delay=...)`
    

Also provide a context-manager-style terminal session ensuring that:

- cursor visibility is restored;
    
- formatting is reset;
    
- Ctrl+C does not leave the cursor hidden.
    

ANSI sequences should be concentrated here.

When stdout is not a TTY, animation methods should print simplified static output instead of emitting control sequences.

---

# 8. `parser.py`

The terminal environment is **not a shell**.

Never execute user-entered strings through `subprocess`, `os.system`, `eval`, or shell parsing.

## Structure

### `ParsedCommand`

Fields:

- `name: str`
    
- `args: tuple[str, ...]`
    
- `raw: str`
    

## Function

### `parse_command(line) -> ParsedCommand`

Behavior:

1. trim whitespace;
    
2. use Python's `shlex.split()` so quoted paths work;
    
3. lowercase the command name only;
    
4. preserve argument capitalization;
    
5. empty input returns an empty/no-op command;
    
6. malformed quoting becomes a normal command error.
    

Example:

```
store "/home/me/My Notes.txt" notes.txt
```

becomes logically:

```
name = "store"
```

Nothing in the parser knows which commands are allowed.

---

# 9. Core game data structures

Place these in `levels.py`.

## `LevelRule`

Fields:

- `command`
    
- `args`
    
- `requires_flags`
    
- `sets_flags`
    
- `message`
    
- `transition_to`
    
- `trap_id`
    
- `hidden`
    

A rule may set a flag, transition, trigger a trap, or a combination where explicitly defined.

## `LevelDefinition`

Fields:

- `id`
    
- `prompt`
    
- `ascii_scene`
    
- `intro_lines`
    
- `visible_commands`
    
- `rules`
    
- `back_target`
    

## `GameState`

Place in `game.py`.

Fields:

- `current_level`
    
- `flags: set[str]`
    
- `consecutive_unknown_commands`
    

Game state is memory-only.

---

# 10. Exact game progression

Implement this game rather than inventing another during implementation.

## Level 1 — `dormant_relay`

Prompt:

```
relay://sleep>
```

Theme:

A dormant communications relay.

Visible commands:

- `help`
    
- `status`
    
- `clear`
    

Hidden command:

- `wake`
    

`status` prints clues including:

```
CARRIER: ASLEEP
```

`wake` transitions to `mirror_chamber`.

Three consecutive unknown commands trigger `signal_scramble`.

### `signal_scramble`

Actions:

1. scramble terminal output;
    
2. clear screen;
    
3. replay the level scene;
    
4. reset the unknown-command counter.
    

No progression reset.

---

## Level 2 — `mirror_chamber`

Prompt:

```
mirror://13>
```

ASCII art represents three sockets or mirrors.

Commands:

- `scan`
    
- `probe`
    
- `back`
    
- `help`
    
- `clear`
    

Initially hidden:

- `enter`
    

`scan` displays:

```
SOCKETS: 03 08 13
```

`probe 13`:

- sets `null_echo_found`;
    
- prints the newly discovered sequence:
    

```
ENTRY CHANNEL ACCEPTS: ENTER NULL
```

`enter null` is recognized only after `null_echo_found`.

Successful `enter null` transitions to `archive_junction`.

`probe 03` or `probe 08` triggers `false_probe`.

### `false_probe`

Actions:

1. fake corruption messages;
    
2. short progress animation;
    
3. reset level-local flags;
    
4. remain in `mirror_chamber`.
    

`back` returns to `dormant_relay`.

---

# 11. Level 3 — `archive_junction`

Prompt:

```
archive://junction>
```

Commands:

- `inspect`
    
- `open`
    
- `back`
    
- `status`
    
- `help`
    
- `clear`
    

`inspect` reveals:

```
WHITE ARCHIVE
```

### `open white`

Transitions to `decoy_archive`.

### `open red`

Triggers `red_purge`.

### `open black`

Transitions to `sealed_archive`.

`back` returns to `mirror_chamber`.

---

# 12. Decoy level — `decoy_archive`

Prompt:

```
archive://verified>
```

Make this area suspiciously normal.

Commands:

- `status`
    
- `read`
    
- `back`
    
- `help`
    
- `clear`
    

`status` returns excessively reassuring fake diagnostics:

```
ARCHIVE STATUS: PERFECT
```

`read index` says:

```
A REAL ARCHIVE WOULD NOT LEAVE THE EXIT OPEN.
```

`back` returns to `archive_junction`.

Nothing in the decoy unlocks the vault.

---

# 13. Level 4 — `sealed_archive`

Prompt:

```
seal://mirror>
```

Commands:

- `inspect`
    
- `read`
    
- `status`
    
- `back`
    
- `help`
    
- `clear`
    

Hidden initially:

- `unlock`
    

`inspect` reveals:

```
SEAL: MIRROR
```

`read seal`:

- sets `seal_read`;
    
- prints:
    

```
THE MIRROR ACCEPTS ONE VERB:
```

`unlock mirror` requires `seal_read`.

Success transitions to the authentication gate.

Any other `unlock <value>` triggers `seal_lockout`.

`back` returns to `archive_junction`.

---

# 14. Game traps

Place trap definitions and dispatch in `traps.py`.

## Structures

### `TrapAction`

Fields:

- `kind`
    
- `value`
    

### `TrapDefinition`

Fields:

- `id`
    
- ordered `actions`
    

### `TrapResult`

Fields:

- `exit_program`
    
- `new_level`
    
- `cooldown_seconds`
    

## Required fake trap types

Implement actions for:

- `clear`
    
- `scramble`
    
- `fake_corruption`
    
- `fake_file_deletion`
    
- `fake_purge`
    
- `fake_shutdown`
    
- `countdown`
    
- `reset_level`
    
- `move_backward`
    
- `lock_vault`
    
- `cooldown`
    
- `exit_program`
    

Fake file-deletion messages must use invented filenames.

They must **never call the vault storage deletion functions**.

Fake corruption/purge/shutdown actions must likewise be presentation-only.

---

# 15. Concrete traps

Define these built-ins.

## `signal_scramble`

```
scramble
```

## `false_probe`

```
fake_corruption
```

## `red_purge`

```
countdown: 5
```

This is entirely fake by default.

## `seal_lockout`

```
fake_corruption
```

The cooldown timestamp goes into `state.json`, so immediately restarting does not bypass it.

## `auth_lockout`

After three unsuccessful password attempts:

```
fake_corruption
```

This lockout is primarily part of the experience; do not present it as meaningful protection against offline password guessing.

---

# 16. `game.py`

## Responsibility

Own:

- current level;
    
- game flags;
    
- command availability;
    
- rule matching;
    
- level transitions;
    
- trap requests.
    

It never decrypts data.

It never performs OS actions.

## Main class

### `GameEngine`

Fields:

- `state`
    
- level definitions
    
- trap dispatcher reference or trap callback
    

Methods:

- `current_level()`
    
- `render_intro(terminal)`
    
- `available_commands()`
    
- `handle(parsed_command)`
    
- `transition(level_id)`
    
- `reset_current_level()`
    
- `move_back()`
    
- `reset_game()`
    

`help` displays only visible commands.

Hidden commands become usable when a matching rule permits them, but do not automatically appear in help unless the preceding clue explicitly reveals them.

Unknown commands increment `consecutive_unknown_commands`.

A recognized command resets that counter.

---

# 17. Trap dispatch boundary

`game.py` should request a trap by ID:

```
"red_purge"
```

It must not implement the trap itself.

`traps.py` then:

1. looks up the trap definition;
    
2. checks whether traps are globally enabled;
    
3. checks `disabled_traps`;
    
4. executes fake/game actions in order;
    
5. updates cooldown state where applicable;
    
6. optionally dispatches an explicitly configured OS action;
    
7. returns an outcome to `main.py`.
    

This preserves the game/vault separation.

---

# 18. Real OS actions

All real machine actions live in:

```
os_actions.py
```

Nowhere else.

## Public API

Expose only:

- `close_terminal()`
    
- `logout()`
    
- `reboot()`
    
- `shutdown()`
    
- `perform_os_action(action_name)`
    

Internally choose the platform with `sys.platform`.

Use fixed platform-native commands/APIs with fixed argument lists.

Never incorporate terminal-game input into an OS command.

Never invoke them with `shell=True`.

## Configuration gate

Defaults:

```
enabled = false
```

A real action is performed only if all conditions are true:

1. `real_os_actions.enabled` is `true`;
    
2. action appears in `allowed_actions`;
    
3. the current trap ID has an explicit binding;
    
4. the platform implementation supports it.
    

Example configuration concept:

```
bindings:
```

No default trap should have a real-machine binding.

### Close-terminal behavior

Terminal-emulator control is inconsistent across platforms.

`close_terminal()` should therefore be explicitly best-effort.

If the current terminal cannot safely be identified and closed, return "unsupported" rather than killing arbitrary parent processes.

Program termination itself remains universally supported through the ordinary `exit_program` trap action.

---

# 19. Cryptography design

Put all cryptographic primitives in:

```
vault/crypto.py
```

No game module imports `cryptography`.

## Password KDF

Use:

**Argon2id**

Fixed version-1 parameters:

```
salt:            16 random bytes
```

Those parameters correspond to RFC 9106's second recommended Argon2id profile: 64 MiB, three iterations and four lanes; a 16-byte salt is also the RFC recommendation. ([RFC Editor](https://www.rfc-editor.org/info/rfc9106/?utm_source=chatgpt.com))

Use the password's UTF-8 bytes as Argon2id input.

Do not invent a secondary password-hashing algorithm.

## Encryption

Use:

**AES-256-GCM**

- 32-byte derived key;
    
- fresh random 12-byte nonce for every encryption operation;
    
- 128-bit GCM authentication tag.
    

The `cryptography` documentation supports 256-bit AES-GCM keys and specifically warns that nonce reuse under the same key compromises security. ([Cryptography](https://cryptography.io/en/latest/hazmat/primitives/aead/?utm_source=chatgpt.com))

---

# 20. Key verification

The password should be checked by decrypting a small authenticated marker.

During `relay init`:

1. generate Argon2id salt;
    
2. derive master key;
    
3. generate random key-check nonce;
    
4. encrypt the constant internal marker:
    

```
relayvault-key-check-v1
```

5. use associated data containing the `vault_id`;
    
6. put nonce and ciphertext/tag in `config.json`.
    

At unlock:

1. derive key from entered password and stored Argon2 parameters;
    
2. attempt authenticated decryption of key-check data;
    
3. if authentication fails, reject the password;
    
4. if it succeeds, load and authenticate the manifest.
    

No password hash needs to be stored separately.

---

# 21. Encrypted record format

Use one binary envelope format for manifests and file objects.

Version 1:

```
offset   size   meaning
```

Record types:

```
1 = encrypted manifest
```

Reject:

- wrong magic;
    
- unsupported version;
    
- unknown record type;
    
- files shorter than the minimum envelope;
    
- failed GCM authentication.
    

---

# 22. Associated authenticated data

Use AES-GCM associated data to bind ciphertext to its intended purpose.

Conceptual values:

Manifest:

```
relayvault:v1:<vault_id>:manifest
```

File:

```
relayvault:v1:<vault_id>:file:<object_id>
```

Key check:

```
relayvault:v1:<vault_id>:key-check
```

This prevents an encrypted object from simply being swapped into another object ID and accepted as the same record.

---

# 23. `vault/crypto.py` functions

Implement:

- `derive_master_key(password, kdf_config)`
    
- `create_key_check(key, vault_id)`
    
- `verify_key_check(key, vault_id, key_check)`
    
- `build_aad(vault_id, record_type, object_id=None)`
    
- `encrypt_bytes(plaintext, key, aad, record_type)`
    
- `decrypt_bytes(blob, key, aad, expected_record_type)`
    
- `encrypt_stream(source, destination, key, aad, record_type)`
    
- `decrypt_stream(source, destination, key, aad, expected_record_type)`
    
- `parse_record_header(...)`
    

Small data such as the manifest can use an in-memory AEAD operation.

Large files should be processed incrementally with `cryptography`'s streaming AES/GCM cipher API rather than loaded completely into RAM.

For streaming decryption, never expose the destination as a completed file until GCM finalization succeeds; the cryptography documentation explicitly cautions that GCM plaintext cannot be trusted before authentication finalization. ([Cryptography](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/?utm_source=chatgpt.com))

Use a 1 MiB I/O chunk size.

---

# 24. `vault/storage.py`

## Responsibility

Filesystem representation of the encrypted vault.

It receives an already-authenticated master key.

It does not prompt for passwords.

## Structures

### `VaultEntry`

Fields:

- `id`
    
- `name`
    
- `size`
    
- `created_at`
    
- `updated_at`
    

### `VaultManifest`

Fields:

- `version`
    
- `entries`
    

## Required functions

- `initialize_empty_vault(paths, key, config)`
    
- `load_manifest(paths, key, config)`
    
- `save_manifest_atomic(paths, key, config, manifest)`
    
- `find_entry(manifest, name)`
    
- `list_entries(manifest)`
    
- `store_file(...)`
    
- `retrieve_file(...)`
    
- `remove_file(...)`
    
- `rename_file(...)`
    
- `validate_vault_name(name)`
    

---

# 25. Vault filename rules

Version 1 supports files only.

Do not implement folders.

Logical vault names:

- must not be empty;
    
- cannot be `.` or `..`;
    
- cannot contain `/`;
    
- cannot contain `\`;
    
- maximum 255 characters;
    
- duplicate exact names are rejected.
    

Stored object IDs are generated using random UUID4 values with dashes removed.

Example:

```
ef18b5388298493482883d096f74f83a.vlt
```

---

# 26. Store operation

Command:

```
store "<source path>" [vault-name]
```

If `vault-name` is absent, use the source basename.

Processing:

1. expand user home in source path;
    
2. verify it exists;
    
3. require a regular file;
    
4. reject directories;
    
5. reject symbolic links;
    
6. validate logical vault name;
    
7. reject duplicate vault name;
    
8. generate random object ID;
    
9. create temporary ciphertext file inside `objects/`;
    
10. stream-encrypt source into it;
    
11. finalize AES-GCM;
    
12. atomically rename temporary ciphertext to `<object_id>.vlt`;
    
13. add manifest entry;
    
14. write encrypted manifest atomically.
    

Crash between object creation and manifest update may leave an orphan encrypted object.

That is acceptable.

Do not automatically delete unknown encrypted objects.

---

# 27. Retrieve operation

Command:

```
retrieve <vault-name> "<destination>"
```

Destination may be:

- a complete output filename; or
    
- an existing directory, in which case use the vault filename.
    

Behavior:

1. look up manifest entry;
    
2. reject existing destination instead of silently overwriting it;
    
3. create hidden temporary output beside the destination;
    
4. decrypt object into temporary output;
    
5. authenticate/finalize GCM;
    
6. verify resulting plaintext size matches manifest;
    
7. atomically rename temporary file to requested destination;
    
8. delete temporary file on any error.
    

The user must never see a partially authenticated decrypted result as the requested destination file.

---

# 28. Remove operation

Command:

```
remove <vault-name>
```

Prompt for confirmation:

```
remove '<name>'? [y/N]
```

On confirmation:

1. remove entry from manifest in memory;
    
2. atomically write updated encrypted manifest;
    
3. only after manifest commit succeeds, delete the encrypted object.
    

A crash after step 2 may leave an orphan ciphertext file, which is harmless.

Do not attempt secure erasure.

Modern filesystems and SSDs make reliable secure deletion difficult; the application should make no such claim.

---

# 29. Rename operation

Command:

```
rename <old-name> <new-name>
```

Only changes the encrypted manifest.

The object ID and ciphertext file stay unchanged.

Update `updated_at`.

---

# 30. Info operation

Command:

```
info <vault-name>
```

Display only:

- logical filename;
    
- plaintext size;
    
- created time;
    
- last metadata update.
    

Do not expose internal object IDs unless running tests/debugging.

---

# 31. `vault/session.py`

This is the user-facing vault-layer coordinator.

## Main class

### `VaultSession`

Fields:

- configuration;
    
- paths;
    
- current decrypted manifest;
    
- master-key buffer;
    
- locked flag;
    
- last-activity monotonic timestamp;
    
- busy flag;
    
- timeout event;
    
- watchdog stop event.
    

## Construction

Provide:

- `VaultSession.authenticate(password, config, paths)`
    

Behavior:

1. derive key;
    
2. verify key check;
    
3. decrypt manifest;
    
4. return an unlocked session.
    

Authentication failure returns a specific authentication exception, not a half-created session.

## Methods

- `list_files()`
    
- `store(source, name=None)`
    
- `retrieve(name, destination)`
    
- `remove(name)`
    
- `rename(old, new)`
    
- `info(name)`
    
- `touch_activity()`
    
- `lock()`
    
- `is_locked()`
    
- `start_auto_lock()`
    
- `stop_auto_lock()`
    

Every file operation first checks `is_locked()`.

---

# 32. Master-key lifetime

The entered password should never be retained after derivation.

The session keeps only the derived key.

Store the session copy in a mutable byte buffer where practical.

On `lock()`:

1. mark session locked;
    
2. stop access to the manifest;
    
3. overwrite the session key buffer with zero bytes as a best-effort measure;
    
4. remove the key reference;
    
5. drop the decrypted manifest.
    

Do **not** claim guaranteed key erasure from RAM.

Python, its allocator, cryptographic libraries, and the operating system may create copies that application code cannot reliably scrub.

---

# 33. Automatic locking

Default:

```
300 seconds
```

Use a tiny standard-library watchdog thread.

Do not introduce asyncio or a terminal framework.

The watchdog:

1. wakes periodically;
    
2. checks monotonic elapsed idle time;
    
3. skips timeout while a storage operation is explicitly marked busy;
    
4. calls `session.lock()` when idle timeout expires;
    
5. sets a `timed_out` event.
    

The key therefore disappears even if the main thread is currently blocked waiting for terminal input.

When the user next interacts, `main.py` sees that the session locked, clears the vault UI, prints a fictional link-loss message, resets the game, and returns to Level 1.

File activity calls `touch_activity()`.

A manual:

```
lock
```

does the same thing immediately.

---

# 34. Temporary plaintext handling

The application should not create decrypted working copies merely for viewing.

Version 1 does **not** implement:

- `edit`;
    
- `open in editor`;
    
- automatic launching of files.
    

That avoids keeping unmanaged plaintext temporary files.

The only plaintext temporary file is the `.partial` file used during explicit retrieval.

Rules:

- create it in the requested destination directory;
    
- give it a random suffix;
    
- never put it inside the vault directory;
    
- delete it on authentication failure or exceptions;
    
- rename only after successful authentication;
    
- clean stale `.partial` files created by the current operation when possible.
    

Do not implement "secure shredding."

---

# 35. Vault command mode

After successful authentication, switch to a visibly different but still themed prompt:

```
core://open>
```

Available commands:

- `list`
    
- `store`
    
- `retrieve`
    
- `remove`
    
- `rename`
    
- `info`
    
- `lock`
    
- `clear`
    
- `help`
    
- `exit`
    

There is no:

- `cd`;
    
- arbitrary shell command;
    
- executable launching;
    
- pipes;
    
- redirection;
    
- command substitution.
    

Unknown commands remain internal unknown commands.

---

# 36. Authentication stage

The authentication gate is a special main-program state rather than another normal level.

Presentation:

1. sealed-gate ASCII art;
    
2. fake synchronization progress;
    
3. line such as:
    

```
IDENTITY MATERIAL REQUIRED
```

Do not print "vault password."

Use `getpass.getpass()` so password input is not echoed.

### Attempt policy

Maximum three attempts in one authentication visit.

On a bad password:

- play a small rejection animation;
    
- increment attempt count.
    

After attempt 3:

- invoke `auth_lockout`;
    
- persist 30-second cooldown;
    
- exit.
    

A successful attempt resets the in-memory count.

---

# 37. Startup cooldown handling

Before showing the first game scene:

1. load `state.json`;
    
2. compare `cooldown_until` to current UTC;
    
3. if still active, show a countdown or refusal screen;
    
4. exit when the short presentation completes;
    
5. if expired, clear `cooldown_until` and continue.
    

No game progress needs to be restored.

---

# 38. First-time initialization

`relay init` should perform exactly this sequence:

1. resolve application paths;
    
2. refuse to overwrite an existing initialized vault;
    
3. create runtime directories;
    
4. prompt for password with `getpass`;
    
5. prompt again;
    
6. reject mismatch;
    
7. reject empty password;
    
8. generate random 16-byte salt;
    
9. create new `vault_id`;
    
10. derive master key;
    
11. create encrypted key-check marker;
    
12. create empty manifest;
    
13. encrypt manifest;
    
14. write `config.json`;
    
15. write empty `state.json`;
    
16. scrub/release session key;
    
17. print a short success message.
    

No password-strength scoring library.

A simple warning for a very short password is enough, but initialization should not invent elaborate password-policy rules for a personal vault.

---

# 39. Main program loop

`main.py` owns application lifecycle.

Conceptual flow only:

```
resolve paths
```

`main.py` is the only module that knows both the game layer and vault-session layer exist.

That is the central separation boundary.

---

# 40. Command flow

For every normal game command:

```
terminal input
```

For vault commands:

```
terminal input
```

No game rule directly calls storage or crypto.

---

# 41. Errors and exceptions

Use a small number of domain exceptions.

Define them in the module that owns them rather than creating a giant exception hierarchy.

Examples:

### `parser.py`

- `CommandParseError`
    

### `config.py`

- `ConfigError`
    

### `vault/crypto.py`

- `VaultFormatError`
    
- `IntegrityError`
    

### `vault/storage.py`

- `StorageError`
    
- `EntryNotFoundError`
    
- `DuplicateEntryError`
    

### `vault/session.py`

- `AuthenticationError`
    
- `VaultLockedError`
    

### `os_actions.py`

- `UnsupportedActionError`
    
- `ActionNotAllowedError`
    

Expected user mistakes should result in themed messages, not Python tracebacks.

Unexpected exceptions should:

1. stop the auto-lock thread;
    
2. lock the vault session if one exists;
    
3. restore terminal cursor;
    
4. restore ANSI state;
    
5. print a small generic failure message;
    
6. terminate non-zero.
    

`--debug` is unnecessary for version 1.

Developers can run tests or execute through Python when they need tracebacks.

---

# 42. Ctrl+C and EOF

Handle `KeyboardInterrupt` and `EOFError` centrally.

If vault is unlocked:

1. call `session.lock()`;
    
2. restore terminal state;
    
3. exit.
    

If still in game mode:

1. restore terminal state;
    
2. exit.
    

Do not trap the user inside the application.

---

# 43. Terminal effects architecture

Effects should always be authored as calls such as:

```
terminal.fake_system_messages(...)
```

Not as:

```
print(...)
```

scattered throughout level and trap code.

ASCII scenes themselves remain multiline constants in `levels.py`.

Animation frames remain tuple/list constants in `levels.py` or `traps.py` alongside the scene that uses them.

No separate asset-management system.

---

# 44. Real action safety boundary

Three hard rules:

### Rule 1

`parser.py` cannot import `os_actions`.

### Rule 2

`game.py` cannot import `os_actions`.

### Rule 3

Only `traps.py` can request `os_actions.perform_os_action()`, and only after validating explicit configuration.

This makes real-machine traps obvious and easy to disable during development.

---

# 45. Build sequence

Implement in this exact order.

## Stage 1 — Package, paths, and configuration

Create:

- `pyproject.toml`
    
- package entry points;
    
- `config.py`;
    
- `__main__.py`.
    

At completion:

- `relay` starts;
    
- `relay init` routing exists;
    
- runtime paths resolve;
    
- JSON config/state can be loaded and saved atomically;
    
- malformed configuration is rejected;
    
- no vault functionality exists yet.
    

Tests:

- default home resolution;
    
- environment override;
    
- config round trip;
    
- malformed config;
    
- state round trip;
    
- atomic replacement behavior.
    

---

## Stage 2 — Terminal effects

Implement `terminal.py`.

At completion, a small development call can:

- print typewriter text;
    
- clear the terminal;
    
- hide/show cursor;
    
- display progress;
    
- animate ASCII frames;
    
- countdown;
    
- scramble text;
    
- gracefully degrade with effects disabled.
    

Tests:

- effects-disabled output;
    
- cursor restoration;
    
- countdown invokes injected sleeper rather than real sleep;
    
- non-TTY mode contains no unwanted ANSI sequences.
    

---

## Stage 3 — Command parser

Implement `parser.py`.

At completion:

- ordinary commands parse;
    
- quoted paths work;
    
- command names normalize to lowercase;
    
- arguments remain intact;
    
- malformed quoting becomes a controlled error;
    
- no input can accidentally become a shell command.
    

Tests:

- zero arguments;
    
- multiple arguments;
    
- quoted filename;
    
- spaces;
    
- uppercase command;
    
- malformed quote;
    
- special shell-looking characters remain ordinary arguments.
    

---

## Stage 4 — Level definitions and game engine

Implement:

- `levels.py`
    
- `game.py`
    

Add all five environments:

- dormant relay;
    
- mirror chamber;
    
- archive junction;
    
- decoy archive;
    
- sealed archive.
    

At completion, with trap dispatch temporarily mocked:

- the entire puzzle path can be played;
    
- hidden commands work;
    
- flags work;
    
- backtracking works;
    
- wrong choices generate trap IDs;
    
- authentication gate can be reached.
    

Tests:

- exact successful route;
    
- `enter null` fails before discovery;
    
- wrong probe triggers `false_probe`;
    
- white archive enters decoy;
    
- black archive progresses;
    
- red archive requests `red_purge`;
    
- wrong seal unlock requests `seal_lockout`.
    

---

## Stage 5 — Fake trap engine

Implement `traps.py`, but keep real OS actions mocked/not active.

At completion:

- every fake trap renders;
    
- cooldowns write `state.json`;
    
- fake purge exits application via a controlled program outcome;
    
- fake deletion never touches files;
    
- traps can be disabled through configuration.
    

Tests:

- action order;
    
- disabled trap;
    
- fake deletion makes zero filesystem deletions;
    
- cooldown timestamp written;
    
- exit result generated;
    
- lock action calls only the provided vault-lock callback.
    

---

## Stage 6 — OS-action isolation

Implement `os_actions.py`.

Then connect its gated dispatch from `traps.py`.

At completion:

- real actions remain disabled by default;
    
- unsupported actions return clean errors;
    
- real actions require global enablement;
    
- action must be allowlisted;
    
- trap must have explicit binding;
    
- no game command can call an OS action directly.
    

Tests must monkeypatch the actual OS invocation.

Automated tests must never reboot, log out, shut down, or close the real terminal.

Test:

- disabled global configuration;
    
- action not allowlisted;
    
- missing binding;
    
- supported mocked action dispatch;
    
- unsupported platform handling.
    

---

## Stage 7 — Cryptographic primitives

Implement `vault/crypto.py`.

At completion:

- Argon2id derives a deterministic key from password/salt;
    
- different salts produce different keys;
    
- key check encrypts/verifies;
    
- small records encrypt/decrypt;
    
- streaming files encrypt/decrypt;
    
- corrupted ciphertext fails authentication;
    
- wrong record types fail;
    
- AAD mismatch fails.
    

Tests:

- KDF known consistency;
    
- wrong password;
    
- random nonce uniqueness over a practical sample;
    
- manifest bytes round trip;
    
- multi-chunk file round trip;
    
- one-byte ciphertext mutation;
    
- modified tag;
    
- wrong object ID/AAD;
    
- truncated file;
    
- bad magic/version.
    

---

## Stage 8 — Vault storage

Implement `vault/storage.py`.

At completion:

- empty encrypted manifest can be created;
    
- files store as opaque random object IDs;
    
- encrypted manifest maps names to IDs;
    
- files retrieve byte-for-byte;
    
- rename works without rewriting ciphertext;
    
- removal works;
    
- duplicate names are rejected;
    
- temporary files are cleaned after failure.
    

Tests:

- initialize;
    
- empty list;
    
- store;
    
- list;
    
- retrieve and compare SHA-256 in the test;
    
- rename;
    
- remove;
    
- duplicate;
    
- missing entry;
    
- invalid logical filename;
    
- symlink rejection;
    
- corrupted object;
    
- existing destination;
    
- failed decryption leaves no completed plaintext destination.
    

---

## Stage 9 — Authentication and vault session

Implement `vault/session.py`.

Complete the `relay init` path.

At completion:

- a real vault can be initialized;
    
- correct password authenticates;
    
- wrong password fails;
    
- password is not stored;
    
- session can perform every vault operation;
    
- manual lock invalidates the session;
    
- operations after lock fail;
    
- watchdog automatically removes access after timeout.
    

Tests:

- initialization;
    
- correct authentication;
    
- incorrect authentication;
    
- modified key check;
    
- manual lock;
    
- locked method rejection;
    
- short test timeout;
    
- watchdog;
    
- busy operation prevents mid-operation timeout;
    
- timeout clears manifest/session key state.
    

---

## Stage 10 — Main integration

Finish `main.py`.

At completion:

1. `relay` displays the mysterious first level;
    
2. complete puzzle route works;
    
3. trap paths work;
    
4. authentication gate works;
    
5. correct password enters vault mode;
    
6. vault commands work;
    
7. `lock` resets to first game level;
    
8. timeout resets to first game level;
    
9. relaunch always begins at first game level;
    
10. cooldown traps survive restart.
    

Add themed vault help and error messages here, not inside crypto/storage.

---

## Stage 11 — End-to-end testing

Write `test_end_to_end.py`.

Use a temporary `VAULTGAME_HOME`.

Programmatically exercise:

```
initialize
```

Also test:

```
wrong puzzle path
```

and:

```
wrong password ×3
```

and:

```
modify encrypted object
```

---

# 46. Specific security tests

Beyond normal unit tests, explicitly verify:

### Plaintext filename hiding

After storing:

```
family-photo.jpg
```

search every filename beneath `vault/`.

The text `family-photo.jpg` should not appear outside decrypted memory.

It may exist inside `manifest.vlt` only as ciphertext.

### Plaintext-content hiding

Store a test file containing a unique marker.

Verify the marker does not appear in the ciphertext object.

### Wrong password

Must not distinguish:

```
almost correct
```

from any other wrong password.

### Ciphertext mutation

Changing one ciphertext byte must make retrieval fail authentication.

### Blob swapping

Copy ciphertext from object A over object B.

Because object IDs participate in AAD, B's retrieval must fail.

### Fake trap isolation

Trigger every fake-destructive trap and compare the encrypted vault directory before/after.

No vault object should change.

---

# 47. What will deliberately not exist

Version 1 should not implement:

- subdirectories inside the vault;
    
- multiple vaults;
    
- multiple users;
    
- password recovery;
    
- networking;
    
- cloud backup;
    
- file synchronization;
    
- file sharing;
    
- GUI;
    
- web UI;
    
- mounting as a filesystem;
    
- transparent disk encryption;
    
- full shell access;
    
- external plugins;
    
- scripting language;
    
- configurable user-authored levels;
    
- encryption algorithm selection;
    
- KDF selection;
    
- external password manager integration;
    
- automatic editor launching;
    
- secure-delete claims;
    
- telemetry;
    
- analytics;
    
- logging of user commands.
    

Those would increase complexity without helping this project's core experience.

---

# 48. README scope

The README should eventually contain only practical information:

- concept;
    
- supported Python version;
    
- install command;
    
- `relay init`;
    
- `relay`;
    
- where data is stored;
    
- how to back up `~/.relayvault/`;
    
- warning that losing the password means losing access;
    
- warning that retrieved plaintext copies are no longer protected by the vault;
    
- explanation that fake destructive effects are fake;
    
- strong warning about real OS trap configuration;
    
- explanation that real OS actions are disabled by default;
    
- test command.
    

Do not explain puzzle solutions in the main README.

Put them only in developer comments/tests if necessary.

---

# 49. Definition of completion

The project is complete when all of the following are true:

- `relay init` creates a usable encrypted vault.
    
- `relay` always starts in the dormant mysterious terminal environment.
    
- The player can progress through the specified levels using only internal commands.
    
- Hidden commands and state-dependent commands behave exactly as specified.
    
- The white archive is a working decoy.
    
- Wrong puzzle choices can produce corruption, purge, countdown, cooldown, screen-clear, backward/reset, and forced-exit effects.
    
- Fake destructive traps cannot modify protected files.
    
- Real logout/reboot/shutdown/terminal actions are isolated in `os_actions.py`, disabled by default, allowlisted, explicitly bound, and never reachable directly from command input.
    
- Authentication uses Argon2id-derived key material rather than a stored password.
    
- Protected contents use authenticated AES-256-GCM encryption.
    
- Stored plaintext filenames are hidden inside the encrypted manifest.
    
- Stored file bytes remain encrypted on disk.
    
- `list`, `store`, `retrieve`, `remove`, `rename`, `info`, and `lock` work.
    
- Corrupted ciphertext is detected rather than decrypted silently.
    
- Retrieval never publishes a partially authenticated output file.
    
- Manual locking destroys the active session's access to the key.
    
- Automatic idle locking works.
    
- Relaunching requires playing the game again.
    
- Cooldown traps survive restart.
    
- Ctrl+C and crashes restore normal terminal cursor/formatting.
    
- No shell commands can be injected through the internal command parser.
    
- All subsystem and end-to-end tests pass.
    
- No database, network service, account system, plugin system, or unnecessary architectural layer has been introduced.
    

At that point, the project is a complete small application: **a terminal-game façade leading to a real, locally encrypted, authenticated personal file vault**, with the two layers remaining cleanly separated.
