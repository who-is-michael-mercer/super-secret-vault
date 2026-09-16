"""Authenticated, in-memory vault access and a monotonic idle watchdog.

Key cleanup is best effort: Python and cryptographic libraries can retain copies.
Manual lock denies new work immediately; already running storage work can finish
with its local references, without restoring access to the locked session.
"""

import threading
import time
from contextlib import contextmanager

from . import crypto, capsule, store as storage
from relayvault.legacy.storage import validate_vault_name
from datetime import datetime, timezone
import uuid
from pathlib import Path


class AuthenticationError(ValueError):
    """The encrypted password verifier did not authenticate."""


class VaultLockedError(ValueError):
    """The session no longer permits vault access."""


class VaultSession:
    @classmethod
    def authenticate(cls, password, path, *, timeout=300, recovery=False):
        opened = storage.Store(path, recovery=recovery)
        try:
            try:
                key = opened.capsule.authenticate(password)
            except capsule.KeyCheckError as error:
                raise AuthenticationError(
                    "Password or authentication metadata did not verify."
                ) from error
            try:
                return cls(opened, key, timeout)
            finally:
                key[:] = bytes(len(key))
        except BaseException:
            opened.close()
            raise
        finally:
            del password

    def __init__(self, opened, key, timeout):
        self.store_backend = opened
        self._manifest = opened.capsule.manifest
        self._key = bytearray(key)
        self.auto_lock_seconds = timeout
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
                    else:
                        self.store_backend.capsule.manifest = None

    def _find(self, manifest, name):
        for entry in manifest["entries"]:
            if entry["name"] == name:
                return entry
        raise storage.StorageError("No such logical filename.")

    def list_files(self):
        with self._operation() as (_, manifest):
            return [
                dict(e) for e in sorted(manifest["entries"], key=lambda e: e["name"])
            ]

    def info(self, name):
        with self._operation() as (_, manifest):
            entry = self._find(manifest, name)
            return {k: entry[k] for k in ("name", "size", "created_at", "updated_at")}

    def verify(self):
        with self._operation() as (key, _):
            return self.store_backend.capsule.verify(key)

    def _commit(self, key, entries, extra=None):
        old = self.store_backend.capsule
        records = [
            (e, extra[1] if extra and e["id"] == extra[0] else old.record(e))
            for e in entries
        ]
        try:
            updated = self.store_backend.commit(key, records)
        except BaseException:
            if self.store_backend.failed:
                self.lock()
            raise
        with self._state_lock:
            if not self._locked:
                self._manifest = updated

    def store(self, source, name=None):
        with self._operation() as (key, manifest):
            path = storage.target_path(source)
            name = path.name if name is None else name
            validate_vault_name(name)
            if any(e["name"] == name for e in manifest["entries"]):
                raise storage.StorageError("Logical filename already exists.")
            if len(manifest["entries"]) >= capsule.MAX_ENTRIES:
                raise storage.StorageError("Entry limit exceeded.")
            if path == self.store_backend.path or path.is_relative_to(
                storage.settings.home().resolve()
            ):
                raise storage.StorageError(
                    "Cannot store Relay state or the active vault."
                )
            identity = uuid.uuid4().hex
            with (
                storage.open_regular(path) as plain,
                storage.temporary(self.store_backend.path.parent) as (encrypted, _),
            ):
                before = storage.identity(plain)
                if before[2] > capsule.MAX_CAPSULE:
                    raise storage.StorageError("File exceeds capsule limit.")
                crypto.encrypt_stream(
                    capsule.Slice(plain, 0, before[2]),
                    encrypted,
                    key,
                    crypto.build_aad(
                        self.store_backend.capsule.header["vault_id"],
                        crypto.FILE,
                        identity,
                    ),
                    crypto.FILE,
                )
                if storage.identity(plain) != before:
                    raise storage.ConcurrentWriteError(
                        "Source changed while encrypting."
                    )
                now = datetime.now(timezone.utc).isoformat()
                entry = dict(
                    id=identity,
                    name=name,
                    size=plain.tell(),
                    created_at=now,
                    updated_at=now,
                )
                self._commit(key, [*manifest["entries"], entry], (identity, encrypted))
            return entry

    def retrieve(self, name, destination):
        with self._operation() as (key, manifest):
            entry = self._find(manifest, name)
            target = storage.target_path(destination)
            if target.is_dir():
                target = storage.target_path(target / entry["name"])
            if target.exists() or target.is_symlink():
                raise storage.StorageError("Destination already exists.")
            if target.is_relative_to(storage.settings.home().resolve()):
                raise storage.StorageError("Plaintext must be outside Relay state.")
            with storage.temporary(target.parent) as (plain, staged):
                record = self.store_backend.capsule.record(entry)
                if capsule.digest(record) != entry["sha256"]:
                    raise crypto.IntegrityError("Ciphertext digest mismatch.")
                crypto.decrypt_stream(
                    record,
                    plain,
                    key,
                    crypto.build_aad(
                        self.store_backend.capsule.header["vault_id"],
                        crypto.FILE,
                        entry["id"],
                    ),
                    crypto.FILE,
                )
                if plain.tell() != entry["size"]:
                    raise crypto.IntegrityError("Decrypted size mismatch.")
                plain.flush()
                storage.os.fsync(plain.fileno())
                storage.publish(staged, target)
            return target

    def remove(self, name):
        with self._operation() as (key, manifest):
            entry = self._find(manifest, name)
            self._commit(
                key, [e for e in manifest["entries"] if e["id"] != entry["id"]]
            )

    def rename(self, old, new):
        with self._operation() as (key, manifest):
            validate_vault_name(new)
            if any(e["name"] == new for e in manifest["entries"]):
                raise storage.StorageError("Logical filename already exists.")
            entry = self._find(manifest, old)
            updated = entry | dict(
                name=new, updated_at=datetime.now(timezone.utc).isoformat()
            )
            self._commit(
                key,
                [updated if e["id"] == entry["id"] else e for e in manifest["entries"]],
            )
            return updated

    def export(self, destination, *, image=None):
        with self._operation() as (key, manifest):
            return self.store_backend.export(key, destination, image=image)

    def close(self):
        self.lock()
        with self._operation_lock:
            self.store_backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

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
        if not self._busy:
            self.store_backend.capsule.manifest = None
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
            self._thread = threading.Thread(
                target=self._watchdog, name="relay-vault-auto-lock", daemon=True
            )
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
        interval = min(1.0, self.auto_lock_seconds)
        while not self._stop.wait(interval):
            with self._state_lock:
                if self._locked:
                    return
                if (
                    not self._busy
                    and time.monotonic() - self._last_activity >= self.auto_lock_seconds
                ):
                    self.lock()
                    self.timed_out.set()
                    return
