"""Relay lifecycle: initialization, the game, and authenticated vault access."""

import argparse
import base64
import getpass
import math
import os
import stat
import sys
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from v2_reference.config import (AppConfig, ConfigError, RuntimeState, resolve_paths,
                              ensure_runtime_directories, is_initialized, load_config,
                              load_runtime_state,
                              save_config_atomic, save_runtime_state_atomic)
from v2_reference.dashboard import render_dashboard
from v2_reference.game import GameEngine
from v2_reference.parser import CommandParseError, parse_command
from v2_reference.terminal import Terminal
from v2_reference.traps import dispatch_trap
from v2_reference.vault import crypto, storage
from v2_reference.vault.session import AuthenticationError, VaultLockedError, VaultSession


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relay", description="Relay terminal vault")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("init", help="Initialize a new encrypted vault")
    args = parser.parse_args(argv)

    if args.command == "init":
        try:
            _initialize()
        except KeyboardInterrupt:
            print("Vault initialization interrupted.", file=sys.stderr)
            return 130
        except (ConfigError, storage.StorageError, crypto.VaultFormatError,
                OSError, EOFError) as error:
            print(f"Vault initialization failed: {error}", file=sys.stderr)
            return 1
        print("Vault initialized.")
        return 0

    return run_application()


def _initialize():
    paths = resolve_paths()
    if is_initialized(paths):
        raise ConfigError("Vault is already initialized.")
    for path in (paths.config_path, paths.state_path, paths.manifest_path):
        if path.exists() or path.is_symlink():
            raise ConfigError("Existing runtime files prevent initialization.")
    for directory in (paths.home, paths.vault_dir, paths.objects_dir):
        if directory.exists() or directory.is_symlink():
            if not stat.S_ISDIR(directory.lstat().st_mode):
                raise ConfigError("Runtime directories must not be symlinks or files.")
    if paths.objects_dir.exists() and any(paths.objects_dir.iterdir()):
        raise ConfigError("Existing vault objects prevent initialization.")
    ensure_runtime_directories(paths)
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not password:
        raise ConfigError("Password must not be empty.")
    if password != confirmation:
        raise ConfigError("Passwords do not match.")
    del confirmation
    identity = uuid.uuid4().hex
    kdf = dict(salt=base64.b64encode(os.urandom(16)).decode("ascii"),
               iterations=3, memory_kib=65536, lanes=4, length=32)
    key = bytearray(crypto.derive_master_key(password, kdf))
    del password
    published = []
    try:
        config = AppConfig(vault_id=identity, kdf=kdf,
            encryption={"algorithm": "AES-256-GCM", "format_version": 1},
            key_check=crypto.create_key_check(bytes(key), identity), auto_lock_seconds=300,
            traps={"enabled": True, "disabled_traps": []},
            real_os_actions={"enabled": False, "allowed_actions": [], "bindings": {}})
        storage.initialize_empty_vault(paths, bytes(key), config)
        published.append((paths.manifest_path, paths.manifest_path.lstat()))
        save_config_atomic(paths, config, exclusive=True)
        published.append((paths.config_path, paths.config_path.lstat()))
        # State is the final completion marker; prior failures stay uninitialized.
        save_runtime_state_atomic(paths, RuntimeState(), exclusive=True)
    except BaseException:
        # Roll back only this invocation's publications, never a replaced path.
        cleanup_error = None
        for path, owned in reversed(published):
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    path.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                cleanup_error = error
        if cleanup_error is not None:
            raise ConfigError("Initialization failed and cleanup was incomplete.") from cleanup_error
        raise
    finally:
        key[:] = b"\0" * len(key)


def _read_input(terminal, reader, prompt):
    terminal.show_cursor()
    try:
        terminal.print(prompt, end=" ")
        return reader()
    finally:
        terminal.hide_cursor()


def run_application(*, terminal=None, input_fn=None, password_fn=None):
    """Run one relay process; injected readers use the usual input/getpass API."""
    terminal = terminal if terminal is not None else Terminal()
    input_fn = input if input_fn is None else input_fn
    password_fn = (lambda: getpass.getpass("")) if password_fn is None else password_fn
    session = None
    try:
        with terminal:
            try:
                paths = resolve_paths()
                initialized = is_initialized(paths)
                config = load_config(paths) if initialized else None
                terminal.progress("relay0: bootstrap", 1.2, skippable=False)
                render_dashboard(terminal, paths, config, now=datetime.now(timezone.utc))
                if not initialized:
                    terminal.print("relay0: setup required; run relay init", style="warning")
                    return 0
                if handle_cooldown(paths, terminal):
                    return 0
                game = GameEngine()
                while run_game_loop(game, terminal, config, paths, input_fn):
                    session = run_authentication_gate(terminal, config, paths, password_fn)
                    if session is None:
                        return 1
                    session.start_auto_lock()
                    if not session.is_locked():
                        terminal.sequence(("key check       ok", "manifest        verified",
                                           "archive         decrypted", "session         active"))
                    outcome = run_vault_loop(session, terminal, input_fn)
                    session.lock()
                    session = None
                    if outcome == "exit":
                        return 0
                    terminal.clear()
                    terminal.print("session: locked (idle timeout)" if outcome == "timeout"
                                   else "session: locked", style="muted")
                    terminal.print("relay0: route reset")
                    game.reset_game()
                return 0
            finally:
                if session is not None:
                    session.lock()
    except (EOFError, KeyboardInterrupt):
        terminal.print("\nrelay0: disconnected")
        return 0
    except (crypto.IntegrityError, crypto.VaultFormatError):
        terminal.print("archive0: integrity check failed; disconnected")
        return 1
    except Exception:
        terminal.print("relay0: failure; disconnected")
        return 1


def handle_cooldown(paths, terminal):
    """Refuse this launch while a persisted UTC cooldown is still active."""
    state = load_runtime_state(paths)
    if state.cooldown_until is None:
        return False
    until = datetime.fromisoformat(state.cooldown_until)
    remaining = (until - datetime.now(timezone.utc)).total_seconds()
    if remaining > 0:
        seconds = math.ceil(remaining)
        terminal.print(f"relay0: backoff {seconds}s", style="warning")
        return True
    save_runtime_state_atomic(paths, replace(state, cooldown_until=None))
    return False


def run_game_loop(game, terminal, config, paths, input_fn):
    """Return True only when the game requests its authentication gate."""
    game.render_intro(terminal)
    while True:
        line = _read_input(terminal, input_fn, game.current_level().prompt)
        try:
            command = parse_command(line)
        except CommandParseError:
            terminal.print("command: invalid quoting")
            continue
        result = game.handle(command)
        if result.message:
            terminal.print(result.message)
        if result.clear:
            terminal.clear()
        if result.authentication_gate:
            return True
        if result.trap_id:
            def move_backward():
                game.move_back()
            trap = dispatch_trap(result.trap_id, terminal, config, paths,
                                 reset_level=game.reset_current_level,
                                 move_backward=move_backward)
            if trap.exit_program:
                return False
            if trap.new_level is not None:
                game.transition(trap.new_level)
            game.render_intro(terminal)
        elif result.transition_to:
            terminal.progress("route: synchronizing", 0.3)
            game.render_intro(terminal)


def run_authentication_gate(terminal, config, paths, password_fn):
    terminal.print("archive0: sealed channel", style="accent")
    terminal.print("keyring: external\nauth: identity material required\n")
    for _ in range(3):
        password = _read_input(terminal, password_fn, "password:")
        try:
            return VaultSession.authenticate(password, config, paths)
        except AuthenticationError:
            terminal.print("auth: key check failed", style="error")
        finally:
            del password
    terminal.print("auth: retry limit exceeded", style="error")
    dispatch_trap("auth_lockout", terminal, config, paths)
    return None


VAULT_HELP = """list                            list protected files
store "<source>" [name]         encrypt and store a file
retrieve <name> "<destination>" decrypt to an explicit destination
remove <name>                   remove a protected file (confirmation required)
rename <old> <new>               rename a protected file
info <name>                     show file metadata
lock                            return to the relay
clear                           clear the terminal
help                            show these commands
exit                            lock and exit"""


def run_vault_loop(session, terminal, input_fn):
    while True:
        if session.is_locked() or session.timed_out.is_set():
            return "timeout"
        line = _read_input(terminal, input_fn, "vault0:/data>")
        if session.is_locked() or session.timed_out.is_set():
            return "timeout"
        try:
            session.touch_activity()
            command = parse_command(line)
            outcome = handle_vault_command(command, session, terminal, input_fn)
            if outcome is not None:
                return outcome
        except CommandParseError:
            terminal.print("command: invalid quoting")
        except VaultLockedError:
            return "timeout"
        except storage.StorageError:
            terminal.print("file: operation refused; check name, paths, destination")
        except OSError:
            terminal.print("file: I/O failed; check access and space")


def _display_text(text):
    """Keep user filenames readable without allowing terminal control injection."""
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in text)


def handle_vault_command(command, session, terminal, input_fn):
    """Dispatch internal commands, returning only lock/exit lifecycle requests."""
    name, args = command.name, command.args
    if not name:
        return None
    if name in {"list", "lock", "clear", "help", "exit"}:
        valid = not args
    elif name == "store":
        valid = len(args) in {1, 2}
    elif name in {"retrieve", "rename"}:
        valid = len(args) == 2
    elif name in {"remove", "info"}:
        valid = len(args) == 1
    else:
        terminal.print("command: unavailable")
        return None
    if not valid:
        terminal.print("usage: " + next(line.strip() for line in VAULT_HELP.splitlines()
                                      if line.startswith(name + " ")))
        return None
    if name in {"lock", "exit"}:
        return name
    if name == "help":
        terminal.print(VAULT_HELP)
    elif name == "clear":
        terminal.clear()
    elif name == "list":
        entries = session.list_files()
        if not entries:
            terminal.print("index: empty")
        for entry in entries:
            terminal.print(f"{_display_text(entry.name)} — {entry.size} bytes")
    elif name == "store":
        session.store(*args)
        terminal.progress("encrypt", 0.3)
        terminal.print("verify     ok\nstore: complete")
    elif name == "retrieve":
        session.retrieve(*args)
        terminal.print("verify     ok")
        terminal.progress("decrypt", 0.3)
        terminal.print(f"write      {_display_text(args[1])}\nretrieve: complete")
    elif name == "remove":
        answer = _read_input(terminal, input_fn, f"remove '{_display_text(args[0])}'? [y/N]")
        if session.is_locked() or session.timed_out.is_set():
            return "timeout"
        session.touch_activity()
        if answer.lower() not in {"y", "yes"}:
            terminal.print("remove: canceled")
        else:
            session.remove(args[0])
            terminal.print("remove: complete")
    elif name == "rename":
        session.rename(*args)
        terminal.print("rename: complete")
    elif name == "info":
        info = session.info(args[0])
        terminal.print(f"name: {_display_text(info['name'])}\nsize: {info['size']} bytes\n"
                       f"created: {info['created_at']}\nupdated: {info['updated_at']}")
    return None
