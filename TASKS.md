# Tasks — Super Secret Vault

Source: `IMPLEMENTATION_PLAN.md`, section 45. These tasks preserve its exact stage order and completion requirements. The plan remains authoritative if this backlog and the plan differ.

Stages 1 through 8 are complete and verified. Stage 9 is unblocked but remains pending; all later stages are outside this pass. Run each stage's relevant pytest checks and fix failures before advancing. Automated tests must never perform real logout, reboot, shutdown, or terminal-closing actions; replace actual OS invocation at the isolation boundary.

## Ordered backlog

- [x] TASK-001: Stage 1 — Package, paths, and configuration <!-- COMPLETE; depends_on: null; agent: tdd-guide; 53 tests passed on Python 3.12.14 and 3.14.7; wheel/entry-point checks passed; reviews approved; no Git metadata -->
- [x] TASK-002: Stage 2 — Terminal effects <!-- COMPLETE; depends_on: TASK-001; agent: tdd-guide; 65 Stage 2 tests and 118 full-suite tests passed on Python 3.12.14 and 3.14.7; wheel/import checks passed; spec and code/Python reviews approved; Stage 1 unchanged -->
- [x] TASK-003: Stage 3 — Command parser <!-- COMPLETE; depends_on: TASK-002; agent: tdd-guide; 33 parser tests and 151 full-suite tests passed on Python 3.12.14 and 3.14.7; wheel/import checks passed; spec and code/Python/security reviews approved; Stages 1 and 2 unchanged -->
- [x] TASK-004: Stage 4 — Level definitions and game engine <!-- COMPLETE; depends_on: TASK-003; agent: tdd-guide; 78 Stage 4 tests and 229 full-suite tests passed on Python 3.12.14 and 3.14.7; wheel/import checks passed; spec and code/Python/security reviews approved; Stages 1–3 unchanged -->
- [x] TASK-005: Stage 5 — Fake trap engine <!-- COMPLETE; depends_on: TASK-004; agent: tdd-guide; 87 Stage 5 tests and 316 full-suite tests passed on Python 3.12.14 and 3.14.7; wheel/import checks passed; spec and code/Python/security reviews approved; config compatibility extension only; no push -->
- [x] TASK-006: Stage 6 — OS-action isolation <!-- COMPLETE; depends_on: TASK-005; agent: tdd-guide; 56 OS-action tests, 152 trap tests, 437 full-suite tests passed on Python 3.12.14 and 3.14.7; guarded tests executed zero real OS actions; wheel/import checks passed; spec and code/Python/security reviews approved -->
- [x] TASK-007: Stage 7 — Cryptographic primitives <!-- COMPLETE; depends_on: TASK-006; agent: tdd-guide; 126 crypto tests and 563 full-suite tests passed on Python 3.12.14 and 3.14.7; installed wheel/independent crypto checks passed; spec, code/Python, and security reviews approved; Stages 1–6 unchanged -->
- [x] TASK-008: Stage 8 — Vault storage <!-- COMPLETE; depends_on: TASK-007; agent: tdd-guide; 133 storage tests, 126 crypto tests, 704 full-suite tests passed on Python 3.12.14 and 3.14.7; installed wheel/manual lifecycle checks passed; spec, code/Python, and security reviews approved; optional vault_id compatibility only; Stage 7 crypto unchanged -->
- [ ] TASK-009: Stage 9 — Authentication and vault session <!-- PENDING; depends_on: TASK-008; agent: tdd-guide -->
- [ ] TASK-010: Stage 10 — Main integration <!-- PENDING; depends_on: TASK-009; agent: tdd-guide -->
- [ ] TASK-011: Stage 11 — End-to-end testing <!-- PENDING; depends_on: TASK-010; agent: e2e-runner -->

## Stage requirements

The stage content below is copied from section 45; each stage must also obey the detailed module requirements elsewhere in the plan.

### TASK-001 — Package, paths, and configuration

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

### TASK-002 — Terminal effects

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

### TASK-003 — Command parser

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

### TASK-004 — Level definitions and game engine

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

### TASK-005 — Fake trap engine

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

### TASK-006 — OS-action isolation

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

### TASK-007 — Cryptographic primitives

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

### TASK-008 — Vault storage

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

### TASK-009 — Authentication and vault session

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

### TASK-010 — Main integration

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

Additional integration validation: exercise every completion item above, including manual/idle reset, restart cooldowns, Ctrl+C/EOF, and terminal restoration. Write the practical README described in section 48 without puzzle solutions.

### TASK-011 — End-to-end testing

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

Final validation: cover all integrated journeys, every specific security test in section 46, and every completion criterion in section 49. Run `python -m pytest` for the full suite and record actual results. Do not mark complete with failed or omitted required tests.

## Final completion gate

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
