"""Flat encrypted storage, with authenticated, non-overwriting retrieval.

Callers supply an authenticated key, configuration with vault_id, and their
current manifest. Mutations update that manifest only after its disk commit.
New files publish with an atomic exclusive hard link followed by staging unlink:
plain rename would overwrite concurrent destinations on Unix. Filesystems that
do not support hard links fail closed. Existing manifests use atomic replacement.
This single-process model has no journal or concurrent-writer coordination.
"""

import json
import os
import stat
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from v2_reference.config import AppConfig, AppPaths
from v2_reference.vault import crypto


class StorageError(ValueError):
    """Invalid storage data or a failed filesystem operation."""


class EntryNotFoundError(StorageError):
    """The requested logical filename is absent."""


class DuplicateEntryError(StorageError):
    """The exact logical filename already exists."""


@dataclass(frozen=True)
class VaultEntry:
    id: str
    name: str
    size: int
    created_at: str
    updated_at: str


@dataclass
class VaultManifest:
    version: int
    entries: list[VaultEntry]


def validate_vault_name(name: str) -> None:
    if (not isinstance(name, str) or not name or name in (".", "..")
            or len(name) > 255 or any(char in name for char in ("/", "\\", "\0"))):
        raise StorageError("Invalid logical vault filename.")
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as error:
        raise StorageError("Vault filenames must be valid UTF-8 text.") from error


def _validate_manifest(manifest: VaultManifest) -> None:
    if (not isinstance(manifest, VaultManifest) or type(manifest.version) is not int
            or manifest.version != 1 or not isinstance(manifest.entries, list)):
        raise StorageError("Invalid version-1 manifest.")
    ids, names = set(), set()
    for item in manifest.entries:
        if not isinstance(item, VaultEntry):
            raise StorageError("Invalid manifest entry.")
        try:
            identity = uuid.UUID(hex=item.id) if isinstance(item.id, str) else None
        except ValueError as error:
            raise StorageError("Invalid object ID.") from error
        if identity is None or identity.hex != item.id or identity.version != 4:
            raise StorageError("Object IDs must be lowercase UUID4 hex.")
        validate_vault_name(item.name)
        if type(item.size) is not int or item.size < 0:
            raise StorageError("Entry size must be a non-negative integer.")
        for timestamp in (item.created_at, item.updated_at):
            try:
                parsed = datetime.fromisoformat(timestamp)
            except (TypeError, ValueError) as error:
                raise StorageError("Entry timestamps must be UTC ISO-8601 text.") from error
            if parsed.utcoffset() != timedelta(0):
                raise StorageError("Entry timestamps must include UTC.")
        if item.id in ids or item.name in names:
            raise StorageError("Duplicate manifest object ID or logical filename.")
        ids.add(item.id)
        names.add(item.name)


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StorageError("Duplicate JSON member in manifest.")
        result[key] = value
    return result


@contextmanager
def _storage_io():
    """Preserve crypto errors while giving filesystem failures a controlled type."""
    try:
        yield
    except OSError as error:
        raise StorageError("Vault filesystem operation failed.") from error


def _directories(paths: AppPaths, *, create=False) -> None:
    for directory in (paths.home, paths.vault_dir, paths.objects_dir):
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise StorageError("Vault directories must be actual directories, not symlinks.")


def _regular(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise StorageError("Expected a regular file, not a symlink or special file.")


@contextmanager
def _open_regular(path: Path):
    _regular(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0))
    try:
        opened = os.fstat(descriptor)
        current = path.lstat()
        if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(current.st_mode)
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
            raise StorageError("File changed or is not a regular file.")
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            yield stream
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _temporary(directory: Path, suffix=".tmp"):
    temporary = tempfile.NamedTemporaryFile(mode="w+b", dir=directory,
                                           prefix=".relay-", suffix=suffix, delete=False)
    path = Path(temporary.name)
    try:
        with temporary:
            yield temporary, path
    finally:
        path.unlink(missing_ok=True)


def _publish_new(temporary: Path, destination: Path) -> None:
    os.link(temporary, destination, follow_symlinks=False)


def _manifest_blob(key: bytes, config: AppConfig, manifest: VaultManifest) -> bytes:
    _validate_manifest(manifest)
    plaintext = json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    return crypto.encrypt_bytes(plaintext, key,
                                crypto.build_aad(config.vault_id, crypto.MANIFEST), crypto.MANIFEST)


def initialize_empty_vault(paths: AppPaths, key: bytes, config: AppConfig) -> VaultManifest:
    """Create an encrypted empty manifest without replacing any existing path."""
    manifest = VaultManifest(1, [])
    blob = _manifest_blob(key, config, manifest)
    with _storage_io():
        _directories(paths, create=True)
        with _temporary(paths.vault_dir) as (stream, temporary):
            stream.write(blob)
            stream.flush()
            stream.close()
            _publish_new(temporary, paths.manifest_path)
    return manifest


def load_manifest(paths: AppPaths, key: bytes, config: AppConfig) -> VaultManifest:
    with _storage_io():
        _directories(paths)
        with _open_regular(paths.manifest_path) as stream:
            plaintext = crypto.decrypt_bytes(stream.read(), key,
                crypto.build_aad(config.vault_id, crypto.MANIFEST), crypto.MANIFEST)
    try:
        data = json.loads(plaintext.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise StorageError("Malformed decrypted manifest JSON.") from error
    if (not isinstance(data, dict) or set(data) != {"version", "entries"}
            or not isinstance(data["entries"], list)):
        raise StorageError("Invalid manifest fields.")
    entries = []
    for item in data["entries"]:
        if not isinstance(item, dict) or set(item) != {"id", "name", "size", "created_at", "updated_at"}:
            raise StorageError("Invalid manifest entry fields.")
        entries.append(VaultEntry(**item))
    manifest = VaultManifest(data["version"], entries)
    _validate_manifest(manifest)
    return manifest


def save_manifest_atomic(paths: AppPaths, key: bytes, config: AppConfig,
                         manifest: VaultManifest) -> None:
    blob = _manifest_blob(key, config, manifest)
    with _storage_io():
        _directories(paths)
        _regular(paths.manifest_path)
        with _temporary(paths.vault_dir) as (stream, temporary):
            stream.write(blob)
            stream.flush()
            stream.close()
            _regular(paths.manifest_path)
            os.replace(temporary, paths.manifest_path)


def find_entry(manifest: VaultManifest, name: str) -> VaultEntry:
    for item in manifest.entries:
        if item.name == name:
            return item
    raise EntryNotFoundError("Logical vault filename not found.")


def list_entries(manifest: VaultManifest) -> list[VaultEntry]:
    return sorted(manifest.entries, key=lambda item: item.name)


def _reject_duplicate(manifest: VaultManifest, name: str) -> None:
    if any(item.name == name for item in manifest.entries):
        raise DuplicateEntryError("Logical vault filename already exists.")


def _path(value) -> Path:
    try:
        path = Path(value).expanduser()
        if "\0" in str(path):
            raise ValueError("NUL in path")
        return path
    except (TypeError, ValueError, RuntimeError) as error:
        raise StorageError("Invalid filesystem path.") from error


def store_file(paths: AppPaths, key: bytes, config: AppConfig, manifest: VaultManifest,
               source, name: str | None = None) -> VaultEntry:
    """Publish ciphertext before its manifest entry; failed commit may leave an orphan."""
    source = _path(source)
    name = source.name if name is None else name
    _validate_manifest(manifest)
    validate_vault_name(name)
    _reject_duplicate(manifest, name)
    identity = uuid.uuid4().hex
    with _storage_io():
        _directories(paths)
        with _open_regular(source) as plaintext:
            with _temporary(paths.objects_dir) as (encrypted, temporary):
                crypto.encrypt_stream(plaintext, encrypted, key,
                    crypto.build_aad(config.vault_id, crypto.FILE, identity), crypto.FILE)
                size = plaintext.tell()
                encrypted.flush()
                encrypted.close()
                _publish_new(temporary, paths.objects_dir / f"{identity}.vlt")
        now = datetime.now(timezone.utc).isoformat()
        item = VaultEntry(identity, name, size, now, now)
        updated = VaultManifest(1, [*manifest.entries, item])
        save_manifest_atomic(paths, key, config, updated)
        manifest.entries = updated.entries
    return item


def retrieve_file(paths: AppPaths, key: bytes, config: AppConfig, manifest: VaultManifest,
                  name: str, destination) -> Path:
    """Authenticate and size-check private staging output before exclusive publication."""
    _validate_manifest(manifest)
    item = find_entry(manifest, name)
    target = _path(destination)
    with _storage_io():
        _directories(paths)
        if target.is_dir():
            target /= item.name
        target = target.parent.resolve() / target.name
        if target.parent.is_relative_to(paths.vault_dir.resolve()):
            raise StorageError("Plaintext retrieval must be outside the vault directory.")
        if target.exists() or target.is_symlink():
            raise StorageError("Retrieval destination already exists.")
        with _open_regular(paths.objects_dir / f"{item.id}.vlt") as encrypted:
            with _temporary(target.parent, ".partial") as (plaintext, temporary):
                crypto.decrypt_stream(encrypted, plaintext, key,
                    crypto.build_aad(config.vault_id, crypto.FILE, item.id), crypto.FILE)
                if plaintext.tell() != item.size:
                    raise StorageError("Decrypted size does not match the manifest.")
                plaintext.flush()
                plaintext.close()
                _publish_new(temporary, target)
    return target


def remove_file(paths: AppPaths, key: bytes, config: AppConfig, manifest: VaultManifest,
                name: str) -> None:
    """Commit removal before unlink; failed unlink may leave an unreferenced object."""
    _validate_manifest(manifest)
    item = find_entry(manifest, name)
    with _storage_io():
        _directories(paths)
        object_path = paths.objects_dir / f"{item.id}.vlt"
        _regular(object_path)
        updated = VaultManifest(1, [entry for entry in manifest.entries if entry.id != item.id])
        save_manifest_atomic(paths, key, config, updated)
        manifest.entries = updated.entries
        _regular(object_path)
        object_path.unlink()


def rename_file(paths: AppPaths, key: bytes, config: AppConfig, manifest: VaultManifest,
                old_name: str, new_name: str) -> VaultEntry:
    _validate_manifest(manifest)
    item = find_entry(manifest, old_name)
    validate_vault_name(new_name)
    _reject_duplicate(manifest, new_name)
    renamed = replace(item, name=new_name, updated_at=datetime.now(timezone.utc).isoformat())
    updated = VaultManifest(1, [renamed if entry.id == item.id else entry for entry in manifest.entries])
    with _storage_io():
        save_manifest_atomic(paths, key, config, updated)
        manifest.entries = updated.entries
    return renamed
