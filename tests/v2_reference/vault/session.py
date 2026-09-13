"""Authenticated, in-memory vault access and a monotonic idle watchdog.

Key cleanup is best effort: Python and cryptographic libraries can retain copies.
Manual lock denies new work immediately; already running storage work can finish
with its local references, without restoring access to the locked session.
"""

import threading
import time
from contextlib import contextmanager

from v2_reference.config import validate_initialized_config
from v2_reference.vault import crypto, storage


class AuthenticationError(ValueError):
    """The encrypted password verifier did not authenticate."""


class VaultLockedError(ValueError):
    """The session no longer permits vault access."""


class VaultSession:
    @classmethod
    def authenticate(cls, password, config, paths):
        config = validate_initialized_config(config)
        key = bytearray(crypto.derive_master_key(password, config.kdf))
        del password
        try:
            try:
                crypto.verify_key_check(bytes(key), config.vault_id, config.key_check)
            except crypto.IntegrityError as error:
                raise AuthenticationError("Password verification failed.") from error
            manifest = storage.load_manifest(paths, bytes(key), config)
            return cls(config, paths, manifest, key)
        finally:
            key[:] = b"\0" * len(key)

    def __init__(self, config, paths, manifest, key):
        self.config = config
        self.paths = paths
        self._manifest = manifest
        self._key = bytearray(key)
        self._locked = False
        self._last_activity = time.monotonic()
        self._busy = False
        self.timed_out = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._state_lock = threading.RLock()
        self._operation_lock = threading.Lock()

    def _require_unlocked(self):
        if self._locked:
            raise VaultLockedError("Vault session is locked.")

    @contextmanager
    def _operation(self):
        # Serialize callers while allowing manual lock to interrupt access, not I/O.
        with self._state_lock:
            self._require_unlocked()
        with self._operation_lock:
            with self._state_lock:
                self._require_unlocked()
                self._busy = True
                key, manifest = bytes(self._key), self._manifest
            try:
                yield key, manifest
            finally:
                with self._state_lock:
                    self._busy = False
                    if not self._locked:
                        self._last_activity = time.monotonic()

    def list_files(self):
        with self._operation() as (_, manifest):
            return storage.list_entries(manifest)

    def info(self, name):
        with self._operation() as (_, manifest):
            entry = storage.find_entry(manifest, name)
            return {"name": entry.name, "size": entry.size,
                    "created_at": entry.created_at, "updated_at": entry.updated_at}

    def store(self, source, name=None):
        with self._operation() as (key, manifest):
            return storage.store_file(self.paths, key, self.config, manifest, source, name)

    def retrieve(self, name, destination):
        with self._operation() as (key, manifest):
            return storage.retrieve_file(self.paths, key, self.config, manifest, name, destination)

    def remove(self, name):
        with self._operation() as (key, manifest):
            return storage.remove_file(self.paths, key, self.config, manifest, name)

    def rename(self, old, new):
        with self._operation() as (key, manifest):
            return storage.rename_file(self.paths, key, self.config, manifest, old, new)

    def touch_activity(self):
        with self._state_lock:
            self._require_unlocked()
            self._last_activity = time.monotonic()

    def is_locked(self):
        with self._state_lock:
            return self._locked

    def _lock_state(self):
        self._locked = True
        if self._key is not None:
            self._key[:] = b"\0" * len(self._key)
        self._key = None
        self._manifest = None
        self._stop.set()

    def lock(self):
        with self._state_lock:
            self._lock_state()
        self.stop_auto_lock()

    def start_auto_lock(self):
        with self._state_lock:
            self._require_unlocked()
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._watchdog,
                                            name="relay-vault-auto-lock", daemon=True)
            self._thread.start()

    def stop_auto_lock(self):
        with self._state_lock:
            self._stop.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        with self._state_lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None

    def _watchdog(self):
        interval = min(1.0, self.config.auto_lock_seconds)
        while not self._stop.wait(interval):
            with self._state_lock:
                if self._locked:
                    return
                if (not self._busy and time.monotonic() - self._last_activity
                        >= self.config.auto_lock_seconds):
                    self.lock()
                    self.timed_out.set()
                    return
