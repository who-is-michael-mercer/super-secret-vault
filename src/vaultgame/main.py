"""Administrative CLI routing for Relay."""

import argparse
import base64
import getpass
import os
import stat
import sys
import uuid

from vaultgame.config import (AppConfig, ConfigError, RuntimeState, resolve_paths,
                              ensure_runtime_directories, is_initialized,
                              save_config_atomic, save_runtime_state_atomic)
from vaultgame.vault import crypto, storage


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

    print(f"Relay package ready. Application data: {resolve_paths().home}")
    return 0


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
