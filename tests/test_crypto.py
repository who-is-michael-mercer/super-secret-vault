"""Fixed-format crypto tests, including independent primitives and failure cleanup."""

import ast
import base64
import io
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vaultgame.vault import crypto

KEY = bytes(range(32))
AAD = b"relayvault:v1:test-vault:manifest"
KDF = {"salt": base64.b64encode(bytes(range(16))).decode("ascii"),
       "iterations": 3, "memory_kib": 65536, "lanes": 4, "length": 32}


def test_real_argon2id():
    original = crypto.derive_master_key("pāssword 🔑", KDF)
    assert len(original) == 32
    assert crypto.derive_master_key("pāssword 🔑", KDF) == original
    assert crypto.derive_master_key("other password", KDF) != original
    assert crypto.derive_master_key("pāssword 🔑", KDF | {
        "salt": base64.b64encode(b"S" * 16).decode("ascii")}) != original


def test_kdf_fixed_parameters_and_utf8(monkeypatch):
    seen = {}

    class KDFSpy:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def derive(self, password):
            seen["password"] = password
            return KEY

    monkeypatch.setattr(crypto, "Argon2id", KDFSpy)
    assert crypto.derive_master_key("e\u0301🔑", KDF) == KEY
    assert seen == {"salt": bytes(range(16)), "iterations": 3,
                    "memory_cost": 65536, "lanes": 4, "length": 32,
                    "password": "e\u0301🔑".encode("utf-8")}


@pytest.mark.parametrize("config", [None, {}, KDF | {"salt": "!"},
    KDF | {"salt": base64.b64encode(b"x" * 15).decode()},
    KDF | {"salt": b"x" * 16}, KDF | {"iterations": True},
    KDF | {"iterations": 4}, KDF | {"memory_kib": 2**60},
    KDF | {"memory_kib": 65536.0}, KDF | {"lanes": 0},
    KDF | {"length": 16}, KDF | {"unexpected": 1}])
def test_bad_kdf_rejected_before_library(config, monkeypatch):
    monkeypatch.setattr(crypto, "Argon2id", lambda **kw: pytest.fail("invalid KDF reached library"))
    with pytest.raises(crypto.VaultFormatError):
        crypto.derive_master_key("password", config)


def test_password_must_be_application_string():
    with pytest.raises(TypeError):
        crypto.derive_master_key(b"password", KDF)


@pytest.mark.parametrize("record_type,object_id,expected", [
    (1, None, b"relayvault:v1:vault:manifest"),
    ("manifest", None, b"relayvault:v1:vault:manifest"),
    (2, "object", b"relayvault:v1:vault:file:object"),
    ("file", "object", b"relayvault:v1:vault:file:object"),
    ("key-check", None, b"relayvault:v1:vault:key-check")])
def test_aad(record_type, object_id, expected):
    assert crypto.build_aad("vault", record_type, object_id) == expected


@pytest.mark.parametrize("vault,kind,object_id", [
    ("", 1, None), ("a:b", 1, None), (None, 1, None),
    ("vault", 2, None), ("vault", 2, ""), ("vault", 2, "a:b"),
    ("vault", "unknown", None), ("vault", True, None),
    ("vault", 1, "unexpected")])
def test_bad_aad(vault, kind, object_id):
    with pytest.raises(crypto.VaultFormatError):
        crypto.build_aad(vault, kind, object_id)


def test_key_check_independently_decrypts_and_verifies():
    check = crypto.create_key_check(KEY, "vault")
    assert set(check) == {"nonce", "ciphertext"}
    nonce = base64.b64decode(check["nonce"], validate=True)
    encrypted = base64.b64decode(check["ciphertext"], validate=True)
    assert len(nonce) == 12
    assert AESGCM(KEY).decrypt(nonce, encrypted, b"relayvault:v1:vault:key-check") == b"relayvault-key-check-v1"
    assert crypto.verify_key_check(KEY, "vault", check) is True
    assert "relayvault-key-check-v1" not in str(check)


@pytest.mark.parametrize("mutation", ["key", "vault", "nonce", "ciphertext", "tag", "marker"])
def test_key_check_authentication_failures(mutation):
    check = crypto.create_key_check(KEY, "vault")
    key, vault = KEY, "vault"
    if mutation == "key":
        key = b"k" * 32
    elif mutation == "vault":
        vault = "different"
    elif mutation == "marker":
        nonce = base64.b64decode(check["nonce"])
        check["ciphertext"] = base64.b64encode(AESGCM(KEY).encrypt(
            nonce, b"wrong marker", b"relayvault:v1:vault:key-check")).decode()
    else:
        field = "nonce" if mutation == "nonce" else "ciphertext"
        data = bytearray(base64.b64decode(check[field]))
        data[-1 if mutation == "tag" else 0] ^= 1
        check[field] = base64.b64encode(data).decode()
    with pytest.raises(crypto.IntegrityError):
        crypto.verify_key_check(key, vault, check)


@pytest.mark.parametrize("check", [None, {}, {"nonce": "!", "ciphertext": "x"},
    {"nonce": base64.b64encode(b"n" * 11).decode(), "ciphertext": base64.b64encode(b"t" * 16).decode()},
    {"nonce": base64.b64encode(b"n" * 12).decode(), "ciphertext": base64.b64encode(b"t" * 15).decode()}])
def test_malformed_key_check(check):
    with pytest.raises(crypto.VaultFormatError):
        crypto.verify_key_check(KEY, "vault", check)


@pytest.mark.parametrize("kind", [1, 2])
@pytest.mark.parametrize("plaintext", [b"", b"hello", b"\0\xff\x80" * 100, bytes(range(256)) * 24])
def test_bytes_and_exact_independent_envelope(kind, plaintext):
    blob = crypto.encrypt_bytes(plaintext, KEY, AAD, kind)
    assert blob[:6] == b"RVLT\x01" + bytes([kind])
    assert len(blob) == 34 + len(plaintext)
    assert crypto.parse_record_header(blob) == (kind, blob[6:18])
    assert len(blob[6:18]) == 12 and len(blob[-16:]) == 16
    assert AESGCM(KEY).decrypt(blob[6:18], blob[18:], AAD) == plaintext
    assert crypto.decrypt_bytes(blob, KEY, AAD, kind) == plaintext


def test_decrypt_independent_envelope():
    nonce = b"n" * 12  # Fixture only, never supplied through production encryption API.
    blob = b"RVLT\x01\x02" + nonce + AESGCM(KEY).encrypt(nonce, b"external", AAD)
    assert crypto.decrypt_bytes(blob, KEY, AAD, 2) == b"external"
    output = io.BytesIO()
    crypto.decrypt_stream(io.BytesIO(blob), output, KEY, AAD, 2)
    assert output.getvalue() == b"external"


@pytest.mark.parametrize("blob", [b"", b"RVLT", b"RVLT\x01\x01" + b"n" * 11,
    b"RVLT\x01\x01" + b"n" * 12, b"RVLT\x01\x01" + b"n" * 12 + b"t" * 15,
    b"NOPE\x01\x01" + b"n" * 12 + b"t" * 16,
    b"RVLT\x02\x01" + b"n" * 12 + b"t" * 16,
    b"RVLT\x01\x03" + b"n" * 12 + b"t" * 16])
def test_structural_record_errors(blob):
    for operation in (lambda: crypto.parse_record_header(blob),
                      lambda: crypto.decrypt_bytes(blob, KEY, AAD, 1),
                      lambda: crypto.decrypt_stream(io.BytesIO(blob), io.BytesIO(), KEY, AAD, 1)):
        with pytest.raises(crypto.VaultFormatError):
            operation()


def test_minimum_envelope_can_be_structural_but_unauthentic():
    blob = b"RVLT\x01\x01" + b"n" * 12 + b"t" * 16
    assert crypto.parse_record_header(blob) == (1, b"n" * 12)
    with pytest.raises(crypto.IntegrityError):
        crypto.decrypt_bytes(blob, KEY, AAD, 1)


@pytest.mark.parametrize("mutation", ["key", "aad", "nonce", "ciphertext", "tag", "trunc_cipher", "trunc_tag"])
def test_byte_authentication_failures(mutation):
    blob, key, aad = corrupted_record(mutation)
    with pytest.raises(crypto.IntegrityError):
        crypto.decrypt_bytes(blob, key, aad, 2)


def corrupted_record(mutation, plaintext=b"plaintext" * 100):
    blob = bytearray(crypto.encrypt_bytes(plaintext, KEY, AAD, 2))
    key, aad = KEY, AAD
    if mutation == "key":
        key = b"k" * 32
    elif mutation == "aad":
        aad = b"wrong"
    elif mutation == "trunc_cipher":
        del blob[18]
    elif mutation == "trunc_tag":
        del blob[-1]
    else:
        blob[{"nonce": 6, "ciphertext": 18, "tag": -1}[mutation]] ^= 1
    return bytes(blob), key, aad


@pytest.mark.parametrize("key", [b"", b"k" * 16, b"k" * 24, b"k" * 31, b"k" * 33, "k" * 32, None])
def test_all_aes_entry_points_reject_non_256_bit_keys(key):
    blob = crypto.encrypt_bytes(b"test", KEY, AAD, 1)
    check = crypto.create_key_check(KEY, "vault")
    for operation in (
        lambda: crypto.create_key_check(key, "vault"),
        lambda: crypto.verify_key_check(key, "vault", check),
        lambda: crypto.encrypt_bytes(b"test", key, AAD, 1),
        lambda: crypto.decrypt_bytes(blob, key, AAD, 1),
        lambda: crypto.encrypt_stream(io.BytesIO(b"test"), io.BytesIO(), key, AAD, 1),
        lambda: crypto.decrypt_stream(io.BytesIO(blob), io.BytesIO(), key, AAD, 1),
    ):
        with pytest.raises(crypto.VaultFormatError):
            operation()


@pytest.mark.parametrize("kind", [0, 3, True, "manifest", None])
def test_invalid_record_type(kind):
    with pytest.raises(crypto.VaultFormatError):
        crypto.encrypt_bytes(b"test", KEY, AAD, kind)
    with pytest.raises(crypto.VaultFormatError):
        crypto.encrypt_stream(io.BytesIO(b"test"), io.BytesIO(), KEY, AAD, kind)


def test_record_type_and_aad_swapping():
    a = crypto.build_aad("vault", 2, "A")
    b = crypto.build_aad("vault", 2, "B")
    blob_a = crypto.encrypt_bytes(b"object A", KEY, a, 2)
    blob_b = crypto.encrypt_bytes(b"object B", KEY, b, 2)
    for blob, wrong_aad in ((blob_a, b), (blob_b, a)):
        with pytest.raises(crypto.IntegrityError):
            crypto.decrypt_bytes(blob, KEY, wrong_aad, 2)
    manifest = crypto.encrypt_bytes(b"manifest", KEY, AAD, 1)
    for operation in (lambda: crypto.decrypt_bytes(manifest, KEY, b, 2),
                      lambda: crypto.decrypt_stream(io.BytesIO(manifest), io.BytesIO(), KEY, b, 2)):
        with pytest.raises(crypto.VaultFormatError):
            operation()
    # Changing the unauthenticated type byte does not defeat purpose-bound AAD.
    forged = manifest[:5] + b"\x02" + manifest[6:]
    with pytest.raises(crypto.IntegrityError):
        crypto.decrypt_bytes(forged, KEY, b, 2)


def test_fresh_nonces_across_all_encryption_operations():
    nonces, envelopes = set(), set()
    for _ in range(32):
        check = crypto.create_key_check(KEY, "vault")
        nonces.add(base64.b64decode(check["nonce"]))
        blob = crypto.encrypt_bytes(b"same", KEY, AAD, 2)
        nonces.add(blob[6:18])
        envelopes.add(blob)
        output = io.BytesIO()
        crypto.encrypt_stream(io.BytesIO(b"same"), output, KEY, AAD, 2)
        nonces.add(output.getvalue()[6:18])
        envelopes.add(output.getvalue())
    assert len(nonces) == 96
    assert len(envelopes) == 64


class BoundedReader(io.BytesIO):
    def __init__(self, data, short=False):
        super().__init__(data)
        self.requests = []
        self.short = short

    def read(self, size=-1):
        assert 0 < size <= 1024 * 1024
        self.requests.append(size)
        return super().read(min(size, 7919) if self.short else size)


@pytest.mark.parametrize("size", [0, 123, 1024 * 1024, 2 * 1024 * 1024 + 37])
@pytest.mark.parametrize("short_reads", [False, True])
def test_stream_round_trip_bounded_and_interoperable(size, short_reads):
    plaintext = (bytes(range(256)) * ((size + 255) // 256))[:size]
    source = BoundedReader(plaintext, short_reads)
    encrypted = io.BytesIO()
    crypto.encrypt_stream(source, encrypted, KEY, AAD, 2)
    blob = encrypted.getvalue()
    assert blob[:6] == b"RVLT\x01\x02"
    assert AESGCM(KEY).decrypt(blob[6:18], blob[18:], AAD) == plaintext
    assert crypto.decrypt_bytes(blob, KEY, AAD, 2) == plaintext
    recovered = io.BytesIO()
    crypto.decrypt_stream(BoundedReader(blob, short_reads), recovered, KEY, AAD, 2)
    assert recovered.getvalue() == plaintext
    if size > 1024 * 1024:
        assert len(source.requests) >= 4


@pytest.mark.parametrize("mutation", ["key", "aad", "nonce", "ciphertext", "tag", "trunc_cipher", "trunc_tag"])
def test_stream_authentication_failure_clears_partial_output(mutation, tmp_path):
    blob, key, aad = corrupted_record(mutation, b"P" * (1024 * 1024 + 10))
    partial = tmp_path / ".retrieved.partial"
    final = tmp_path / "retrieved.bin"
    with partial.open("w+b") as destination:
        with pytest.raises(crypto.IntegrityError):
            crypto.decrypt_stream(io.BytesIO(blob), destination, key, aad, 2)
        assert destination.tell() == 0
    assert partial.read_bytes() == b""
    assert not final.exists()


@pytest.mark.parametrize("encrypt", [True, False])
def test_stream_rejects_nonempty_destination_without_mutation(encrypt):
    data = b"original destination"
    destination = io.BytesIO(data)
    source = io.BytesIO(b"input" if encrypt else crypto.encrypt_bytes(b"input", KEY, AAD, 2))
    function = crypto.encrypt_stream if encrypt else crypto.decrypt_stream
    with pytest.raises(ValueError):
        function(source, destination, KEY, AAD, 2)
    assert destination.getvalue() == data


@pytest.mark.parametrize("encrypt", [True, False])
def test_stream_rejects_same_source_destination(encrypt):
    source = io.BytesIO()
    function = crypto.encrypt_stream if encrypt else crypto.decrypt_stream
    with pytest.raises(ValueError):
        function(source, source, KEY, AAD, 2)


@pytest.mark.parametrize("failure", [OSError("read failed"), KeyboardInterrupt()])
@pytest.mark.parametrize("encrypt", [True, False])
def test_stream_read_failures_cleanup(encrypt, failure):
    data = b"X" * (2 * 1024 * 1024)
    if not encrypt:
        data = crypto.encrypt_bytes(data, KEY, AAD, 2)

    class FailingReader(io.BytesIO):
        def read(self, size=-1):
            if self.tell() >= 1024 * 1024 and size > 16:
                raise failure
            return super().read(size)

    destination = io.BytesIO()
    function = crypto.encrypt_stream if encrypt else crypto.decrypt_stream
    with pytest.raises(type(failure)):
        function(FailingReader(data), destination, KEY, AAD, 2)
    assert destination.getvalue() == b""


@pytest.mark.parametrize("encrypt", [True, False])
def test_stream_write_failure_cleanup(encrypt):
    class FailingWriter(io.BytesIO):
        def write(self, data):
            if self.tell() > 20:
                raise OSError("write failed")
            return super().write(data)

    plaintext = b"X" * (2 * 1024 * 1024)
    source = io.BytesIO(plaintext if encrypt else crypto.encrypt_bytes(plaintext, KEY, AAD, 2))
    destination = FailingWriter()
    with pytest.raises(OSError, match="write failed"):
        (crypto.encrypt_stream if encrypt else crypto.decrypt_stream)(source, destination, KEY, AAD, 2)
    assert destination.getvalue() == b""


def test_stream_short_writes_are_completed():
    class ShortWriter(io.BytesIO):
        def write(self, data):
            return super().write(data[:7])

    encrypted = ShortWriter()
    crypto.encrypt_stream(io.BytesIO(b"short writes" * 20), encrypted, KEY, AAD, 2)
    decrypted = ShortWriter()
    crypto.decrypt_stream(io.BytesIO(encrypted.getvalue()), decrypted, KEY, AAD, 2)
    assert decrypted.getvalue() == b"short writes" * 20


def test_stream_from_current_source_position():
    encrypted = io.BytesIO()
    crypto.encrypt_stream(io.BytesIO(b"payload"), encrypted, KEY, AAD, 2)
    source = io.BytesIO(b"prefix" + encrypted.getvalue())
    source.seek(6)
    output = io.BytesIO()
    crypto.decrypt_stream(source, output, KEY, AAD, 2)
    assert output.getvalue() == b"payload"


def test_crypto_architecture_and_no_secret_output(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    check = crypto.create_key_check(KEY, "vault")
    crypto.verify_key_check(KEY, "vault", check)
    crypto.decrypt_bytes(crypto.encrypt_bytes(b"secret plaintext", KEY, AAD, 1), KEY, AAD, 1)
    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr() == ("", "")
    tree = ast.parse(Path(crypto.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module]
            assert all(name.split(".")[0] in {"base64", "binascii", "os", "typing", "cryptography"} for name in names)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            assert name not in {"eval", "exec", "system", "Popen", "print", "open", "unlink", "remove"}


def test_nist_aes256_gcm_known_answer(monkeypatch):
    # NIST CAVS 14, pyca vectors/ciphers/AES/GCM/gcmEncryptExtIV256.rsp, first case.
    key = bytes.fromhex("b52c505a37d78eda5dd34f20c22540ea1b58963cf8e5bf8ffa85f9f2492505b4")
    nonce = bytes.fromhex("516c33929df5a3284ff463d7")
    tag = bytes.fromhex("bdc1ac884d332457a1d2664f168c76f0")
    requests = []

    def deterministic_fixture(size):
        requests.append(size)
        return nonce

    monkeypatch.setattr(crypto.os, "urandom", deterministic_fixture)
    expected = b"RVLT\x01\x01" + nonce + tag
    assert crypto.encrypt_bytes(b"", key, b"", 1) == expected
    output = io.BytesIO()
    crypto.encrypt_stream(io.BytesIO(), output, key, b"", 1)
    assert output.getvalue() == expected
    assert requests == [12, 12]
    assert crypto.decrypt_bytes(expected, key, b"", 1) == b""


@pytest.mark.parametrize("blob,size", [(b"", 34), (b"x" * 19, 34),
    (b"RVLT\x01\x01" + b"n" * 12, 33), (b"x" * 18, True), (None, None)])
def test_header_explicit_size_validation(blob, size):
    with pytest.raises(crypto.VaultFormatError):
        crypto.parse_record_header(blob, size)


@pytest.mark.parametrize("encrypt", [True, False])
@pytest.mark.parametrize("capability", ["seekable", "writable"])
def test_destination_requires_staging_capabilities(encrypt, capability):
    class InadequateDestination(io.BytesIO):
        def seekable(self):
            return capability != "seekable"

        def writable(self):
            return capability != "writable"

    destination = InadequateDestination()
    source = io.BytesIO(b"data" if encrypt else crypto.encrypt_bytes(b"data", KEY, AAD, 2))
    with pytest.raises(ValueError, match="staging"):
        (crypto.encrypt_stream if encrypt else crypto.decrypt_stream)(source, destination, KEY, AAD, 2)
    assert destination.getvalue() == b""


def test_decrypt_source_must_be_seekable():
    class UnseekableSource(io.BytesIO):
        def seekable(self):
            return False

    with pytest.raises(ValueError, match="source must be seekable"):
        crypto.decrypt_stream(UnseekableSource(), io.BytesIO(), KEY, AAD, 2)


@pytest.mark.parametrize("written", [None, 0, -1, 10**9])
def test_invalid_write_result_never_succeeds(written):
    class InvalidWriter(io.BytesIO):
        def write(self, data):
            super().write(data[:1])
            return written

    destination = InvalidWriter()
    with pytest.raises(OSError):
        crypto.encrypt_stream(io.BytesIO(b"data"), destination, KEY, AAD, 2)
    assert destination.getvalue() == b""


def test_cleanup_error_is_visible_and_chains_authentication_failure():
    class CleanupFailure(io.BytesIO):
        def truncate(self, size=None):
            raise OSError("staging cleanup failed")

    blob, key, aad = corrupted_record("tag")
    destination = CleanupFailure()
    with pytest.raises(OSError, match="staging cleanup failed") as failure:
        crypto.decrypt_stream(io.BytesIO(blob), destination, key, aad, 2)
    assert isinstance(failure.value.__context__, crypto.IntegrityError)


def test_truncated_source_during_read_clears_partial_plaintext():
    blob = crypto.encrypt_bytes(b"X" * (1024 * 1024 + 50), KEY, AAD, 2)

    class TruncatedSource(io.BytesIO):
        def read(self, size=-1):
            if self.tell() == 18 + 1024 * 1024:
                return b""
            return super().read(size)

    destination = io.BytesIO()
    with pytest.raises(crypto.VaultFormatError):
        crypto.decrypt_stream(TruncatedSource(blob), destination, KEY, AAD, 2)
    assert destination.getvalue() == b""


def test_non_ascii_base64_and_unencodable_id_rejected():
    with pytest.raises(crypto.VaultFormatError):
        crypto.derive_master_key("password", KDF | {"salt": "é"})
    with pytest.raises(crypto.VaultFormatError):
        crypto.build_aad("\ud800", 1)
