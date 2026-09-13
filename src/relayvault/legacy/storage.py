"""Legacy logical metadata validators; no writable directory backend."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid


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
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or len(name) > 255
        or any(char in name for char in ("/", "\\", "\0"))
    ):
        raise StorageError("Invalid logical vault filename.")
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as error:
        raise StorageError("Vault filenames must be valid UTF-8 text.") from error


def _validate_manifest(manifest: VaultManifest) -> None:
    if (
        not isinstance(manifest, VaultManifest)
        or type(manifest.version) is not int
        or manifest.version != 1
        or not isinstance(manifest.entries, list)
    ):
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
                raise StorageError(
                    "Entry timestamps must be UTC ISO-8601 text."
                ) from error
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
