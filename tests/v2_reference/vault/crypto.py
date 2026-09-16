"""Fixed version-1 Argon2id and AES-256-GCM primitives.

Streaming destinations are fresh, empty, seekable binary staging streams. They
must remain private until this function returns successfully. On failure their
contents are truncated; callers own closing/unlinking the staging file and final
publication. No file paths, storage layout, or password state are managed here.
"""

import base64
import binascii
import os
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

MAGIC = b"RVLT"
FORMAT_VERSION = 1
MANIFEST = 1
FILE = 2
KEY_SIZE = 32
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
HEADER_SIZE = 18
MIN_RECORD_SIZE = HEADER_SIZE + TAG_SIZE
CHUNK_SIZE = 1024 * 1024
KEY_CHECK_MARKER = b"relayvault-key-check-v1"


class VaultFormatError(ValueError):
    """Malformed configuration, key, AAD identity, or encrypted envelope."""


class IntegrityError(ValueError):
    """Authentication failed; no decrypted content may be trusted."""


def _decode_base64(value: str) -> bytes:
    if not isinstance(value, str):
        raise VaultFormatError("Expected base64 text.")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, binascii.Error) as error:
        raise VaultFormatError("Invalid base64 data.") from error


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != KEY_SIZE:
        raise VaultFormatError("AES-256-GCM requires a 32-byte key.")


def _validate_record_type(record_type: int) -> None:
    if type(record_type) is not int or record_type not in (MANIFEST, FILE):
        raise VaultFormatError("Unknown record type.")


def derive_master_key(password: str, kdf_config: dict) -> bytes:
    """Derive a key using the exact version-1 profile and a base64 16-byte salt."""
    expected = {"iterations": 3, "memory_kib": 65536, "lanes": 4, "length": KEY_SIZE}
    if not isinstance(kdf_config, dict) or set(kdf_config) != set(expected) | {"salt"}:
        raise VaultFormatError("Invalid version-1 KDF configuration.")
    for name, value in expected.items():
        if type(kdf_config[name]) is not int or kdf_config[name] != value:
            raise VaultFormatError("Unsupported version-1 KDF parameters.")
    salt = _decode_base64(kdf_config["salt"])
    if len(salt) != SALT_SIZE:
        raise VaultFormatError("Argon2id requires a 16-byte salt.")
    if not isinstance(password, str):
        raise TypeError("Password must be a string.")
    kdf = Argon2id(salt=salt, length=kdf_config["length"],
                   iterations=kdf_config["iterations"], lanes=kdf_config["lanes"],
                   memory_cost=kdf_config["memory_kib"])
    return kdf.derive(password.encode("utf-8"))


def build_aad(vault_id: str, record_type: int | str, object_id: str | None = None) -> bytes:
    """Bind a record to delimiter-free opaque IDs, never to plaintext filenames."""
    if not isinstance(vault_id, str) or not vault_id or ":" in vault_id:
        raise VaultFormatError("Invalid vault ID.")
    if type(record_type) is int and record_type in (MANIFEST, FILE):
        record_type = "manifest" if record_type == MANIFEST else "file"
    if record_type not in ("manifest", "file", "key-check"):
        raise VaultFormatError("Unknown AAD record type.")
    identity = f"relayvault:v1:{vault_id}:{record_type}"
    if record_type == "file":
        if not isinstance(object_id, str) or not object_id or ":" in object_id:
            raise VaultFormatError("File AAD requires an unambiguous object ID.")
        identity += f":{object_id}"
    elif object_id is not None:
        raise VaultFormatError("Only file AAD accepts an object ID.")
    try:
        return identity.encode("utf-8")
    except UnicodeEncodeError as error:
        raise VaultFormatError("IDs must be valid UTF-8 text.") from error


def create_key_check(key: bytes, vault_id: str) -> dict[str, str]:
    """Return JSON-compatible nonce and ciphertext/tag fields, both base64 text."""
    _validate_key(key)
    aad = build_aad(vault_id, "key-check")
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, KEY_CHECK_MARKER, aad)
    return {"nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii")}


def verify_key_check(key: bytes, vault_id: str, key_check: dict[str, str]) -> bool:
    """Return True for the authenticated marker, otherwise raise a controlled error."""
    _validate_key(key)
    aad = build_aad(vault_id, "key-check")
    if not isinstance(key_check, dict) or set(key_check) != {"nonce", "ciphertext"}:
        raise VaultFormatError("Invalid key-check fields.")
    nonce = _decode_base64(key_check["nonce"])
    ciphertext = _decode_base64(key_check["ciphertext"])
    if len(nonce) != NONCE_SIZE or len(ciphertext) < TAG_SIZE:
        raise VaultFormatError("Invalid key-check boundaries.")
    try:
        marker = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as error:
        raise IntegrityError("Key-check authentication failed.") from error
    if marker != KEY_CHECK_MARKER:
        raise IntegrityError("Key-check marker mismatch.")
    return True


def parse_record_header(blob: bytes, record_size: int | None = None) -> tuple[int, bytes]:
    """Return (record type, nonce), validating a complete blob or header plus size.

    Streaming callers may supply exactly HEADER_SIZE bytes and the measured total
    record_size. No plaintext or ciphertext authentication occurs in this parser.
    """
    if not isinstance(blob, bytes):
        raise VaultFormatError("Record data must be bytes.")
    size = len(blob) if record_size is None else record_size
    if type(size) is not int or size < MIN_RECORD_SIZE or len(blob) < HEADER_SIZE:
        raise VaultFormatError("Truncated encrypted record.")
    if record_size is not None and len(blob) != HEADER_SIZE:
        raise VaultFormatError("Expected exactly one record header.")
    if blob[:4] != MAGIC:
        raise VaultFormatError("Invalid record magic.")
    if blob[4] != FORMAT_VERSION:
        raise VaultFormatError("Unsupported record version.")
    _validate_record_type(blob[5])
    return blob[5], blob[6:HEADER_SIZE]


def _header(record_type: int, nonce: bytes) -> bytes:
    return MAGIC + bytes((FORMAT_VERSION, record_type)) + nonce


def encrypt_bytes(plaintext: bytes, key: bytes, aad: bytes, record_type: int) -> bytes:
    _validate_key(key)
    _validate_record_type(record_type)
    nonce = os.urandom(NONCE_SIZE)
    return _header(record_type, nonce) + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt_bytes(blob: bytes, key: bytes, aad: bytes, expected_record_type: int) -> bytes:
    _validate_key(key)
    _validate_record_type(expected_record_type)
    record_type, nonce = parse_record_header(blob)
    if record_type != expected_record_type:
        raise VaultFormatError("Unexpected record type.")
    try:
        return AESGCM(key).decrypt(nonce, blob[HEADER_SIZE:], aad)
    except InvalidTag as error:
        raise IntegrityError("Record authentication failed.") from error


def _prepare_destination(source: BinaryIO, destination: BinaryIO) -> None:
    if source is destination:
        raise ValueError("Source and destination must be different streams.")
    if not destination.seekable() or not destination.writable():
        raise ValueError("Destination must be a seekable writable staging stream.")
    position = destination.tell()
    size = destination.seek(0, os.SEEK_END)
    destination.seek(position)
    if size != 0:
        raise ValueError("Destination staging stream must be empty.")
    destination.seek(0)


def _write_all(destination: BinaryIO, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = destination.write(remaining)
        if not isinstance(written, int) or written <= 0 or written > len(remaining):
            raise OSError("Destination failed to write encrypted/decrypted data.")
        remaining = remaining[written:]


def _read_exact(source: BinaryIO, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = source.read(remaining)
        if not chunk or len(chunk) > remaining:
            raise VaultFormatError("Truncated or invalid encrypted record.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def encrypt_stream(source: BinaryIO, destination: BinaryIO, key: bytes,
                   aad: bytes, record_type: int) -> None:
    """Encrypt from the source's current position into an empty staging stream."""
    _validate_key(key)
    _validate_record_type(record_type)
    _prepare_destination(source, destination)
    try:
        nonce = os.urandom(NONCE_SIZE)
        encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(aad)
        _write_all(destination, _header(record_type, nonce))
        while chunk := source.read(CHUNK_SIZE):
            _write_all(destination, encryptor.update(chunk))
        _write_all(destination, encryptor.finalize())
        _write_all(destination, encryptor.tag)
    except BaseException:
        destination.seek(0)
        destination.truncate(0)
        raise


def decrypt_stream(source: BinaryIO, destination: BinaryIO, key: bytes,
                   aad: bytes, expected_record_type: int) -> None:
    """Authenticate a seekable source record, clearing staging output on failure.

    The envelope starts at the source's current position and ends at EOF. Only
    after successful return may the caller publish its private staging output.
    Cleanup failure propagates with the original error chained; the caller must
    still close and unlink its staging file on any exception.
    """
    _validate_key(key)
    _validate_record_type(expected_record_type)
    _prepare_destination(source, destination)
    if not source.seekable():
        raise ValueError("Encrypted source must be seekable.")
    try:
        start = source.tell()
        end = source.seek(0, os.SEEK_END)
        source.seek(start)
        record_type, nonce = parse_record_header(_read_exact(source, HEADER_SIZE), end - start)
        if record_type != expected_record_type:
            raise VaultFormatError("Unexpected record type.")
        source.seek(end - TAG_SIZE)
        tag = _read_exact(source, TAG_SIZE)
        source.seek(start + HEADER_SIZE)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(aad)
        remaining = end - start - MIN_RECORD_SIZE
        while remaining:
            chunk = _read_exact(source, min(CHUNK_SIZE, remaining))
            remaining -= len(chunk)
            _write_all(destination, decryptor.update(chunk))
        try:
            _write_all(destination, decryptor.finalize())
        except InvalidTag as error:
            raise IntegrityError("Record authentication failed.") from error
    except BaseException:
        destination.seek(0)
        destination.truncate(0)
        raise
