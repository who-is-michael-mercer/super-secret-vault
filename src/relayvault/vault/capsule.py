"""Bounded, self-contained encrypted snapshot codec. See docs/FORMAT.md."""

import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import struct
import uuid

from . import crypto
from relayvault.legacy.config import AppConfig, validate_initialized_config
from relayvault.legacy.storage import (
    VaultEntry,
    VaultManifest,
    _validate_manifest,
    _unique_json_object,
)

MAGIC = b"RLYCAP01"
END = b"RLYEND01"
PREFIX = struct.Struct(">8sIQ")
FOOTER = struct.Struct(">8sQ32s")
MAX_CAPSULE = 1024**3
MAX_HEADER = 65536
MAX_MANIFEST = 16 * 1024**2
MAX_ENTRIES = 10000
CHUNK = crypto.CHUNK_SIZE


class KeyCheckError(crypto.IntegrityError):
    """Password or key-check metadata did not authenticate."""


class FormatError(ValueError):
    """Invalid or unsupported snapshot framing/metadata."""


def encode(data):
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def decode(data):
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                FormatError("Non-finite JSON.")
            ),
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise FormatError("Malformed snapshot JSON.") from error


def exact(source, size):
    return crypto._read_exact(source, size)


class Slice(io.RawIOBase):
    """Independent cursor over a bounded region; never closes the owner stream."""

    def __init__(self, source, offset, size):
        self.source, self.offset, self.size, self.position = source, offset, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=os.SEEK_SET):
        position = offset + (
            0
            if whence == os.SEEK_SET
            else (
                self.position
                if whence == os.SEEK_CUR
                else self.size if whence == os.SEEK_END else -(10**30)
            )
        )
        if not 0 <= position <= self.size:
            raise FormatError("Seek outside record.")
        self.position = position
        return position

    def read(self, size=-1):
        size = (
            self.size - self.position
            if size is None or size < 0
            else min(size, self.size - self.position)
        )
        self.source.seek(self.offset + self.position)
        result = self.source.read(size)
        self.position += len(result)
        return result


def digest(source):
    source.seek(0)
    result = hashlib.sha256()
    while data := source.read(CHUNK):
        result.update(data)
    source.seek(0)
    return result.hexdigest()


def copy(source, destination):
    source.seek(0)
    while data := source.read(CHUNK):
        crypto._write_all(destination, data)


def metadata(password):
    vault_id = uuid.uuid4().hex
    kdf = dict(
        salt=base64.b64encode(os.urandom(16)).decode(),
        iterations=3,
        memory_kib=65536,
        lanes=4,
        length=32,
    )
    key = bytearray(crypto.derive_master_key(password, kdf))
    header = dict(
        vault_id=vault_id,
        kdf=kdf,
        encryption={"algorithm": "AES-256-GCM", "format_version": 1},
        key_check=crypto.create_key_check(bytes(key), vault_id),
    )
    return header, key


def validate_header(header):
    if not isinstance(header, dict) or set(header) != {
        "vault_id",
        "kdf",
        "encryption",
        "key_check",
    }:
        raise FormatError("Invalid public header fields.")
    try:
        validate_initialized_config(AppConfig(**header, auto_lock_seconds=300))
    except (ValueError, TypeError) as error:
        raise FormatError("Unsupported cryptographic metadata.") from error
    return header


class Capsule:
    def __init__(self, source):
        self.source = source
        self.size = source.seek(0, os.SEEK_END)
        if not PREFIX.size + FOOTER.size <= self.size <= MAX_CAPSULE:
            raise FormatError("Invalid capsule size.")
        source.seek(0)
        magic, header_len, manifest_len = PREFIX.unpack(exact(source, PREFIX.size))
        if magic != MAGIC:
            raise FormatError("Unsupported capsule format.")
        if (
            not 1 <= header_len <= MAX_HEADER
            or not crypto.MIN_RECORD_SIZE <= manifest_len <= MAX_MANIFEST
        ):
            raise FormatError("Invalid header or manifest length.")
        self.objects_offset = PREFIX.size + header_len + manifest_len
        self.objects_size = self.size - FOOTER.size - self.objects_offset
        if self.objects_size < 0:
            raise FormatError("Truncated capsule.")
        self.header_bytes = exact(source, header_len)
        self.header = validate_header(decode(self.header_bytes))
        self.manifest_record = Slice(source, PREFIX.size + header_len, manifest_len)
        source.seek(self.size - FOOTER.size)
        end, length, checksum = FOOTER.unpack(exact(source, FOOTER.size))
        if (
            end != END
            or length != self.size
            or bytes.fromhex(digest(Slice(source, 0, self.size - FOOTER.size)))
            != checksum
        ):
            raise FormatError("Capsule completeness checksum failed.")
        self.manifest = None

    def authenticate(self, password):
        key = bytearray(crypto.derive_master_key(password, self.header["kdf"]))
        try:
            try:
                crypto.verify_key_check(
                    bytes(key), self.header["vault_id"], self.header["key_check"]
                )
            except crypto.IntegrityError as error:
                raise KeyCheckError(
                    "Password or authentication metadata did not verify."
                ) from error
            self.unlock(bytes(key))
            return key
        except BaseException:
            key[:] = bytes(len(key))
            raise

    def unlock(self, key):
        self.manifest_record.seek(0)
        plain = crypto.decrypt_bytes(
            self.manifest_record.read(),
            key,
            crypto.build_aad(self.header["vault_id"], crypto.MANIFEST),
            crypto.MANIFEST,
        )
        manifest = decode(plain)
        self.validate_manifest(manifest)
        self.manifest = manifest
        return manifest

    def validate_manifest(self, value):
        fields = {
            "version",
            "snapshot_id",
            "generation",
            "created_at",
            "header_sha256",
            "entries",
        }
        if (
            not isinstance(value, dict)
            or set(value) != fields
            or type(value["version"]) is not int
            or value["version"] != 2
        ):
            raise FormatError("Invalid manifest schema.")
        if type(value["generation"]) is not int or not 1 <= value["generation"] < 2**63:
            raise FormatError("Invalid generation.")
        try:
            identity = uuid.UUID(hex=value["snapshot_id"])
            if identity.version != 4 or identity.hex != value["snapshot_id"]:
                raise ValueError()
            timestamp = datetime.fromisoformat(value["created_at"])
            if timestamp.utcoffset() != timezone.utc.utcoffset(None):
                raise ValueError()
        except (ValueError, TypeError, AttributeError) as error:
            raise FormatError("Invalid snapshot identity/time.") from error
        if value["header_sha256"] != hashlib.sha256(self.header_bytes).hexdigest():
            raise crypto.IntegrityError("Public header authentication failed.")
        entries = value["entries"]
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
            raise FormatError("Too many entries.")
        offset = 0
        logical = []
        base_fields = {"id", "name", "size", "created_at", "updated_at"}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != base_fields | {
                "offset",
                "length",
                "sha256",
            }:
                raise FormatError("Invalid entry fields.")
            if (
                type(entry["offset"]) is not int
                or entry["offset"] != offset
                or type(entry["length"]) is not int
                or entry["length"] < crypto.MIN_RECORD_SIZE
            ):
                raise FormatError("Invalid or overlapping object ranges.")
            if (
                type(entry["size"]) is not int
                or entry["length"] != entry["size"] + crypto.MIN_RECORD_SIZE
            ):
                raise FormatError("Object length disagrees with plaintext size.")
            offset += entry["length"]
            if offset > self.objects_size:
                raise FormatError("Object extends past snapshot.")
            checksum = entry["sha256"]
            if (
                not isinstance(checksum, str)
                or len(checksum) != 64
                or any(c not in "0123456789abcdef" for c in checksum)
            ):
                raise FormatError("Invalid ciphertext checksum.")
            logical.append(VaultEntry(**{k: entry[k] for k in base_fields}))
        if offset != self.objects_size:
            raise FormatError("Unreferenced bytes in snapshot.")
        try:
            _validate_manifest(VaultManifest(1, logical))
        except ValueError as error:
            raise FormatError("Invalid logical manifest.") from error

    def record(self, entry):
        return Slice(
            self.source, self.objects_offset + entry["offset"], entry["length"]
        )

    def verify(self, key):
        self.unlock(key)
        for entry in self.manifest["entries"]:
            record = self.record(entry)
            if digest(record) != entry["sha256"]:
                raise crypto.IntegrityError("Ciphertext digest mismatch.")
            size = crypto.verify_stream(
                record,
                key,
                crypto.build_aad(self.header["vault_id"], crypto.FILE, entry["id"]),
                crypto.FILE,
            )
            if size != entry["size"]:
                raise crypto.IntegrityError("Object size mismatch.")
        return self.manifest


def write(destination, header, key, records, *, generation=1):
    """Write metadata + (logical entry, seekable ciphertext stream) pairs."""
    validate_header(header)
    header_bytes = encode(header)
    if len(header_bytes) > MAX_HEADER or len(records) > MAX_ENTRIES:
        raise FormatError("Snapshot metadata limit exceeded.")
    entries = []
    offset = 0
    for logical, stream in records:
        length = stream.seek(0, os.SEEK_END)
        checksum = digest(stream)
        entry = {
            k: logical[k] for k in ("id", "name", "size", "created_at", "updated_at")
        }
        entries.append(entry | dict(offset=offset, length=length, sha256=checksum))
        offset += length
    manifest = dict(
        version=2,
        snapshot_id=uuid.uuid4().hex,
        generation=generation,
        created_at=datetime.now(timezone.utc).isoformat(),
        header_sha256=hashlib.sha256(header_bytes).hexdigest(),
        entries=entries,
    )
    encrypted = crypto.encrypt_bytes(
        encode(manifest),
        key,
        crypto.build_aad(header["vault_id"], crypto.MANIFEST),
        crypto.MANIFEST,
    )
    size = PREFIX.size + len(header_bytes) + len(encrypted) + offset + FOOTER.size
    if size > MAX_CAPSULE or len(encrypted) > MAX_MANIFEST:
        raise FormatError("Snapshot exceeds supported size.")
    destination.seek(0)
    destination.truncate()
    crypto._write_all(
        destination, PREFIX.pack(MAGIC, len(header_bytes), len(encrypted))
    )
    crypto._write_all(destination, header_bytes)
    crypto._write_all(destination, encrypted)
    for _, stream in records:
        copy(stream, destination)
    checksum = bytes.fromhex(digest(Slice(destination, 0, size - FOOTER.size)))
    destination.seek(size - FOOTER.size)
    crypto._write_all(destination, FOOTER.pack(END, size, checksum))
    destination.flush()
    capsule = Capsule(destination)
    capsule.verify(key)
    return capsule
