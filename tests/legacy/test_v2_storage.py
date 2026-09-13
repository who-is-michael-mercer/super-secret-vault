"""Storage tests use synthetic data and isolated temporary files only."""

import json
import os
import stat
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from v2_reference.config import AppConfig, resolve_paths
from v2_reference.vault import crypto, storage

KEY = bytes(range(32))
NOW = "2026-09-09T12:00:00+00:00"


@pytest.fixture
def vault(tmp_path):
    paths = resolve_paths(tmp_path / "application")
    config = AppConfig(vault_id="test-vault")
    manifest = storage.initialize_empty_vault(paths, KEY, config)
    return paths, config, manifest


def entry(name="notes.txt", **changes):
    return replace(storage.VaultEntry(uuid.uuid4().hex, name, 3, NOW, NOW), **changes)


def put(vault, tmp_path, data=b"test bytes", name="notes.txt"):
    paths, config, manifest = vault
    source = tmp_path / "source"
    source.write_bytes(data)
    return storage.store_file(paths, KEY, config, manifest, source, name)


def object_path(vault, item):
    return vault[0].objects_dir / f"{item.id}.vlt"


def write_manifest(vault, data):
    paths, config, _ = vault
    plaintext = data if isinstance(data, bytes) else json.dumps(data).encode()
    paths.manifest_path.write_bytes(crypto.encrypt_bytes(
        plaintext, KEY, crypto.build_aad(config.vault_id, crypto.MANIFEST), crypto.MANIFEST))


def test_initialize_empty_vault(tmp_path):
    paths = resolve_paths(tmp_path / "new")
    config = AppConfig(vault_id="test-vault")
    manifest = storage.initialize_empty_vault(paths, KEY, config)
    assert manifest == storage.VaultManifest(1, [])
    assert storage.load_manifest(paths, KEY, config) == manifest
    assert paths.objects_dir.is_dir()
    assert paths.manifest_path.read_bytes().startswith(b"RVLT\x01\x01")
    assert sorted(path.name for path in paths.vault_dir.iterdir()) == ["manifest.vlt", "objects"]
    assert not paths.config_path.exists()
    assert not paths.state_path.exists()


def test_initialization_refuses_overwrite(vault):
    paths, config, _ = vault
    original = paths.manifest_path.read_bytes()
    with pytest.raises(storage.StorageError):
        storage.initialize_empty_vault(paths, KEY, config)
    assert paths.manifest_path.read_bytes() == original


def test_manifest_round_trip_fresh_nonce_and_deterministic_json(vault):
    paths, config, manifest = vault
    manifest.entries = [entry(), entry("Résumé.pdf")]
    plaintexts = []
    ciphertexts = []
    for _ in range(2):
        storage.save_manifest_atomic(paths, KEY, config, manifest)
        ciphertexts.append(paths.manifest_path.read_bytes())
        plaintexts.append(crypto.decrypt_bytes(ciphertexts[-1], KEY,
            crypto.build_aad(config.vault_id, crypto.MANIFEST), crypto.MANIFEST))
        assert storage.load_manifest(paths, KEY, config) == manifest
    assert ciphertexts[0] != ciphertexts[1]
    assert plaintexts[0] == plaintexts[1]
    assert json.loads(plaintexts[0]) == asdict(manifest)
    assert b'"source"' not in plaintexts[0]


@pytest.mark.parametrize("name", ["", ".", "..", "../secret", "foo/bar", "foo\\bar", "x" * 256, "a\0b", "\ud800", None, 2])
def test_invalid_names(name):
    with pytest.raises(storage.StorageError):
        storage.validate_vault_name(name)


@pytest.mark.parametrize("name", ["notes.txt", "My Notes.txt", "Résumé.pdf", "x" * 255, "A", "a"])
def test_valid_names(name):
    storage.validate_vault_name(name)


@pytest.mark.parametrize("data", [None, [], {}, {"version": 2, "entries": []},
    {"version": True, "entries": []}, {"version": 1, "entries": {}},
    {"version": 1, "entries": [], "extra": 0}, {"version": 1, "entries": [None]}])
def test_malformed_manifest_structure(vault, data):
    write_manifest(vault, data)
    with pytest.raises(storage.StorageError):
        storage.load_manifest(vault[0], KEY, vault[1])


@pytest.mark.parametrize("field,value", [("id", "../escape"), ("id", uuid.uuid1().hex),
    ("id", uuid.uuid4().hex.upper()), ("id", "0" * 32), ("name", "../bad"),
    ("size", -1), ("size", True), ("size", 1.5), ("created_at", "yesterday"),
    ("updated_at", "2026-09-09T12:00:00"), ("updated_at", "2026-09-09T12:00:00+01:00")])
def test_malformed_entry(vault, field, value):
    item = asdict(entry())
    item[field] = value
    write_manifest(vault, {"version": 1, "entries": [item]})
    with pytest.raises(storage.StorageError):
        storage.load_manifest(vault[0], KEY, vault[1])


@pytest.mark.parametrize("data", [b"{", b"\xff", b'{"version":1,"version":1,"entries":[]}'])
def test_malformed_manifest_json(vault, data):
    write_manifest(vault, data)
    with pytest.raises(storage.StorageError):
        storage.load_manifest(vault[0], KEY, vault[1])


@pytest.mark.parametrize("duplicate", ["id", "name"])
def test_duplicate_manifest_entries_rejected(vault, duplicate):
    first = entry()
    second = replace(entry("different"), **{duplicate: getattr(first, duplicate)})
    manifest = storage.VaultManifest(1, [first, second])
    original = vault[0].manifest_path.read_bytes()
    with pytest.raises(storage.StorageError):
        storage.save_manifest_atomic(vault[0], KEY, vault[1], manifest)
    assert vault[0].manifest_path.read_bytes() == original
    write_manifest(vault, asdict(manifest))
    with pytest.raises(storage.StorageError):
        storage.load_manifest(vault[0], KEY, vault[1])


@pytest.mark.parametrize("mutation,error", [(0, crypto.VaultFormatError), (-1, crypto.IntegrityError)])
def test_manifest_crypto_errors_preserved(vault, mutation, error):
    blob = bytearray(vault[0].manifest_path.read_bytes())
    blob[mutation] ^= 1
    vault[0].manifest_path.write_bytes(blob)
    with pytest.raises(error):
        storage.load_manifest(vault[0], KEY, vault[1])


def test_find_and_list(vault):
    manifest = vault[2]
    manifest.entries = [entry("z"), entry("a"), entry("A")]
    assert [item.name for item in storage.list_entries(manifest)] == ["A", "a", "z"]
    assert [item.name for item in manifest.entries] == ["z", "a", "A"]
    assert storage.find_entry(manifest, "a") is manifest.entries[1]
    with pytest.raises(storage.EntryNotFoundError):
        storage.find_entry(manifest, "missing")


@pytest.mark.parametrize("data", [b"", b"hello", bytes(range(256)), bytes(range(256)) * 8193])
def test_store_retrieve_round_trip(vault, tmp_path, data):
    item = put(vault, tmp_path, data)
    assert len(item.id) == 32 and uuid.UUID(hex=item.id).version == 4
    assert uuid.UUID(hex=item.id).hex == item.id
    assert object_path(vault, item).name == f"{item.id}.vlt"
    assert crypto.parse_record_header(object_path(vault, item).read_bytes())[0] == crypto.FILE
    assert item.size == len(data)
    assert item.created_at == item.updated_at
    assert datetime.fromisoformat(item.created_at).utcoffset().total_seconds() == 0
    assert vault[2].entries == [item]
    assert storage.load_manifest(vault[0], KEY, vault[1]) == vault[2]
    destination = tmp_path / "retrieved"
    assert storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, destination) == destination
    assert destination.read_bytes() == data


def test_default_basename_and_home_expansion(vault, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    source = tmp_path / "My Notes.txt"
    source.write_bytes(b"notes")
    item = storage.store_file(vault[0], KEY, vault[1], vault[2], "~/My Notes.txt")
    assert item.name == "My Notes.txt"
    output = tmp_path / "output"
    output.mkdir()
    result = storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, "~/output")
    assert result == output / item.name
    assert result.read_bytes() == b"notes"


def test_exact_duplicate_and_case_distinct(vault, tmp_path):
    put(vault, tmp_path, name="A")
    with pytest.raises(storage.DuplicateEntryError):
        put(vault, tmp_path, name="A")
    put(vault, tmp_path, name="a")
    assert [item.name for item in storage.list_entries(vault[2])] == ["A", "a"]


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "fifo"])
def test_invalid_source(vault, tmp_path, kind):
    source = tmp_path / "bad"
    if kind == "directory":
        source.mkdir()
    elif kind == "symlink":
        real = tmp_path / "real"
        real.write_bytes(b"data")
        source.symlink_to(real)
    elif kind == "fifo":
        os.mkfifo(source)
    with pytest.raises(storage.StorageError):
        storage.store_file(vault[0], KEY, vault[1], vault[2], source)
    assert vault[2].entries == []
    assert list(vault[0].objects_dir.iterdir()) == []


def test_store_encryption_failure_cleans_temp(vault, tmp_path, monkeypatch):
    def fail(source, destination, *args):
        destination.write(b"incomplete")
        raise OSError("encryption write failed")
    monkeypatch.setattr(crypto, "encrypt_stream", fail)
    with pytest.raises(storage.StorageError):
        put(vault, tmp_path)
    assert vault[2].entries == []
    assert storage.load_manifest(vault[0], KEY, vault[1]).entries == []
    assert list(vault[0].objects_dir.iterdir()) == []


def test_store_publishes_object_before_manifest_failure(vault, tmp_path, monkeypatch):
    original = vault[0].manifest_path.read_bytes()
    def fail(paths, key, config, manifest):
        assert len(manifest.entries) == 1
        assert object_path(vault, manifest.entries[0]).is_file()
        assert storage.load_manifest(paths, key, config).entries == []
        raise OSError("manifest failure")
    monkeypatch.setattr(storage, "save_manifest_atomic", fail)
    with pytest.raises(storage.StorageError):
        put(vault, tmp_path)
    assert vault[0].manifest_path.read_bytes() == original
    assert vault[2].entries == []
    assert len(list(vault[0].objects_dir.glob("*.vlt"))) == 1
    assert len(list(vault[0].objects_dir.iterdir())) == 1


@pytest.mark.parametrize("mutation", [6, 18, -1, "truncate", "short"])
def test_failed_retrieve_cleans_plaintext(vault, tmp_path, mutation):
    item = put(vault, tmp_path, b"sensitive synthetic content")
    path = object_path(vault, item)
    blob = bytearray(path.read_bytes())
    if mutation == "truncate":
        blob = blob[:-4]
    elif mutation == "short":
        blob = blob[:10]
    else:
        blob[mutation] ^= 1
    path.write_bytes(blob)
    original_manifest = vault[0].manifest_path.read_bytes()
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    with pytest.raises((crypto.IntegrityError, crypto.VaultFormatError)):
        storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, output_dir / "final")
    assert list(output_dir.iterdir()) == []
    assert path.read_bytes() == blob
    assert vault[0].manifest_path.read_bytes() == original_manifest


def test_size_mismatch_cleans_plaintext(vault, tmp_path):
    item = put(vault, tmp_path)
    vault[2].entries[0] = replace(item, size=item.size + 1)
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(storage.StorageError):
        storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, output / "final")
    assert list(output.iterdir()) == []


def test_retrieve_publication_waits_for_authentication(vault, tmp_path, monkeypatch):
    item = put(vault, tmp_path)
    target = tmp_path / "result"
    real_decrypt = crypto.decrypt_stream
    def observe(source, destination, *args):
        assert not target.exists()
        assert Path(destination.name).parent == target.parent
        assert Path(destination.name).name.startswith(".")
        assert stat.S_IMODE(os.fstat(destination.fileno()).st_mode) == 0o600
        real_decrypt(source, destination, *args)
        assert not target.exists()
    monkeypatch.setattr(crypto, "decrypt_stream", observe)
    storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, target)
    assert target.read_bytes() == b"test bytes"


@pytest.mark.parametrize("kind", ["file", "symlink", "race"])
def test_retrieve_never_overwrites_destination(vault, tmp_path, monkeypatch, kind):
    item = put(vault, tmp_path)
    target = tmp_path / "result"
    if kind == "symlink":
        target.symlink_to(tmp_path / "absent")
    elif kind == "file":
        target.write_bytes(b"existing")
    else:
        real_decrypt = crypto.decrypt_stream
        def race(source, destination, *args):
            real_decrypt(source, destination, *args)
            target.write_bytes(b"existing")
        monkeypatch.setattr(crypto, "decrypt_stream", race)
    with pytest.raises(storage.StorageError):
        storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, target)
    if kind == "symlink":
        assert target.is_symlink()
    else:
        assert target.read_bytes() == b"existing"
    assert not list(tmp_path.glob(".*.partial"))


@pytest.mark.parametrize("inside", ["vault", "objects", "symlink"])
def test_retrieve_refuses_plaintext_inside_vault(vault, tmp_path, inside):
    item = put(vault, tmp_path)
    if inside == "symlink":
        directory = tmp_path / "alias"
        directory.symlink_to(vault[0].vault_dir, target_is_directory=True)
    else:
        directory = vault[0].vault_dir if inside == "vault" else vault[0].objects_dir
    with pytest.raises(storage.StorageError):
        storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, directory / "plain")
    assert not (directory / "plain").exists()


def test_remove_commits_manifest_before_unlink(vault, tmp_path, monkeypatch):
    item = put(vault, tmp_path)
    path = object_path(vault, item)
    unlink = Path.unlink
    def observe(target, *args, **kwargs):
        if target == path:
            assert storage.load_manifest(vault[0], KEY, vault[1]).entries == []
            assert vault[2].entries == []
        return unlink(target, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", observe)
    storage.remove_file(vault[0], KEY, vault[1], vault[2], item.name)
    assert not path.exists()
    assert vault[2].entries == []


@pytest.mark.parametrize("operation", ["remove", "rename"])
def test_manifest_failure_preserves_object_and_caller(vault, tmp_path, monkeypatch, operation):
    item = put(vault, tmp_path)
    path = object_path(vault, item)
    original = path.read_bytes(), vault[0].manifest_path.read_bytes()
    def fail(*args):
        raise OSError("manifest save failed")
    monkeypatch.setattr(storage, "save_manifest_atomic", fail)
    with pytest.raises(storage.StorageError):
        if operation == "remove":
            storage.remove_file(vault[0], KEY, vault[1], vault[2], item.name)
        else:
            storage.rename_file(vault[0], KEY, vault[1], vault[2], item.name, "new")
    assert (path.read_bytes(), vault[0].manifest_path.read_bytes()) == original
    assert vault[2].entries == [item]


def test_remove_failed_unlink_leaves_orphan_after_commit(vault, tmp_path, monkeypatch):
    item = put(vault, tmp_path)
    path = object_path(vault, item)
    unlink = Path.unlink
    def fail(target, *args, **kwargs):
        if target == path:
            raise PermissionError("deletion denied")
        return unlink(target, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(storage.StorageError):
        storage.remove_file(vault[0], KEY, vault[1], vault[2], item.name)
    assert path.is_file()
    assert vault[2].entries == []
    assert storage.load_manifest(vault[0], KEY, vault[1]).entries == []


def test_rename_only_changes_metadata(vault, tmp_path, monkeypatch):
    item = put(vault, tmp_path)
    path = object_path(vault, item)
    original = path.read_bytes()
    class Clock(datetime):
        @staticmethod
        def now(tz):
            return datetime(2030, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(storage, "datetime", Clock)
    renamed = storage.rename_file(vault[0], KEY, vault[1], vault[2], item.name, "renamed")
    assert renamed.id == item.id
    assert renamed.created_at == item.created_at
    assert renamed.updated_at == "2030-01-01T00:00:00+00:00"
    assert path.read_bytes() == original
    assert storage.find_entry(vault[2], "renamed") == renamed
    with pytest.raises(storage.EntryNotFoundError):
        storage.find_entry(vault[2], item.name)
    assert b"renamed" not in vault[0].manifest_path.read_bytes()


@pytest.mark.parametrize("target,error", [("other", storage.DuplicateEntryError), ("bad/name", storage.StorageError), ("notes.txt", storage.DuplicateEntryError)])
def test_rename_rejects_bad_target(vault, tmp_path, target, error):
    item = put(vault, tmp_path)
    put(vault, tmp_path, name="other")
    with pytest.raises(error):
        storage.rename_file(vault[0], KEY, vault[1], vault[2], item.name, target)


@pytest.mark.parametrize("operation", ["remove", "retrieve", "rename"])
def test_missing_entry(vault, tmp_path, operation):
    with pytest.raises(storage.EntryNotFoundError):
        if operation == "remove":
            storage.remove_file(vault[0], KEY, vault[1], vault[2], "missing")
        elif operation == "retrieve":
            storage.retrieve_file(vault[0], KEY, vault[1], vault[2], "missing", tmp_path / "result")
        else:
            storage.rename_file(vault[0], KEY, vault[1], vault[2], "missing", "new")


def test_no_plaintext_name_or_content_leakage(vault, tmp_path):
    marker = b"RELAY-STORAGE-PLAINTEXT-MARKER-7F291"
    put(vault, tmp_path, marker, "family-photo.jpg")
    for path in vault[0].home.rglob("*"):
        assert "family-photo.jpg" not in path.name
        if path.is_file():
            content = path.read_bytes()
            assert marker not in content
            assert b"family-photo.jpg" not in content
            assert KEY not in content


def test_blob_swapping_rejected(vault, tmp_path):
    first = put(vault, tmp_path, b"one", "A")
    second = put(vault, tmp_path, b"two", "B")
    object_path(vault, second).write_bytes(object_path(vault, first).read_bytes())
    with pytest.raises(crypto.IntegrityError):
        storage.retrieve_file(vault[0], KEY, vault[1], vault[2], "B", tmp_path / "result")
    assert not (tmp_path / "result").exists()
    assert not list(tmp_path.glob(".*.partial"))


def test_file_cannot_replace_manifest(vault, tmp_path):
    item = put(vault, tmp_path)
    vault[0].manifest_path.write_bytes(object_path(vault, item).read_bytes())
    with pytest.raises(crypto.VaultFormatError):
        storage.load_manifest(vault[0], KEY, vault[1])


@pytest.mark.parametrize("operation", ["retrieve", "remove"])
@pytest.mark.parametrize("kind", ["symlink", "missing", "directory", "fifo"])
def test_unexpected_object_path_rejected(vault, tmp_path, operation, kind):
    item = put(vault, tmp_path)
    path = object_path(vault, item)
    original_manifest = vault[0].manifest_path.read_bytes()
    data = path.read_bytes()
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(data)
    if kind == "symlink":
        path.symlink_to(outside)
    elif kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    with pytest.raises(storage.StorageError):
        if operation == "retrieve":
            storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, tmp_path / "result")
        else:
            storage.remove_file(vault[0], KEY, vault[1], vault[2], item.name)
    assert outside.read_bytes() == data
    assert vault[0].manifest_path.read_bytes() == original_manifest
    assert vault[2].entries == [item]


def test_atomic_manifest_replacement_is_encrypted_and_cleans_failure(vault, monkeypatch):
    paths, config, manifest = vault
    old = paths.manifest_path.read_bytes()
    replace_file = os.replace
    replacements = []
    def fail(source, destination):
        source = Path(source)
        assert source.parent == paths.manifest_path.parent
        assert source.read_bytes().startswith(b"RVLT")
        assert paths.manifest_path.read_bytes() == old
        replacements.append(source)
        raise OSError("replace failed")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(storage.StorageError):
        storage.save_manifest_atomic(paths, KEY, config, manifest)
    assert paths.manifest_path.read_bytes() == old
    assert replacements and not replacements[0].exists()
    monkeypatch.setattr(os, "replace", replace_file)
    storage.save_manifest_atomic(paths, KEY, config, manifest)
    assert paths.manifest_path.read_bytes() != old


def test_retrieve_resolves_destination_parent_before_staging(vault, tmp_path, monkeypatch):
    item = put(vault, tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(output, target_is_directory=True)
    decrypt = crypto.decrypt_stream
    def retarget(source, destination, *args):
        decrypt(source, destination, *args)
        alias.unlink()
        alias.symlink_to(vault[0].vault_dir, target_is_directory=True)
    monkeypatch.setattr(crypto, "decrypt_stream", retarget)
    result = storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, alias / "result")
    assert result == output / "result"
    assert result.read_bytes() == b"test bytes"
    assert sorted(path.name for path in output.iterdir()) == ["result"]
    assert not (vault[0].vault_dir / "result").exists()
    assert not list(vault[0].vault_dir.glob("*.partial"))


@pytest.mark.parametrize("failure", [OSError("disk failure"), KeyboardInterrupt(), crypto.IntegrityError("bad tag")])
def test_retrieve_cleans_partial_on_io_interrupt_and_crypto_failure(vault, tmp_path, monkeypatch, failure):
    item = put(vault, tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    original = vault[0].manifest_path.read_bytes(), object_path(vault, item).read_bytes()
    def fail(source, destination, *args):
        destination.write(b"unauthenticated partial bytes")
        destination.flush()
        raise failure
    monkeypatch.setattr(crypto, "decrypt_stream", fail)
    expected = storage.StorageError if isinstance(failure, OSError) else type(failure)
    with pytest.raises(expected):
        storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, output / "final")
    assert list(output.iterdir()) == []
    assert (vault[0].manifest_path.read_bytes(), object_path(vault, item).read_bytes()) == original


def test_bounded_stream_reads_and_actual_size(vault, tmp_path, monkeypatch):
    original = crypto.encrypt_stream, crypto.decrypt_stream
    reads = {"encrypt": [], "decrypt": []}
    class BoundedReader:
        def __init__(self, wrapped, kind):
            self.wrapped = wrapped
            self.kind = kind
        def read(self, size=-1):
            assert 0 < size <= crypto.CHUNK_SIZE
            reads[self.kind].append(size)
            return self.wrapped.read(size)
        def __getattr__(self, name):
            return getattr(self.wrapped, name)
    def encrypt(source, destination, *args):
        # The entry must record bytes actually read, not an earlier stat size.
        with (tmp_path / "source").open("ab") as append:
            append.write(b"appended")
        original[0](BoundedReader(source, "encrypt"), destination, *args)
    def decrypt(source, destination, *args):
        original[1](BoundedReader(source, "decrypt"), destination, *args)
    monkeypatch.setattr(crypto, "encrypt_stream", encrypt)
    monkeypatch.setattr(crypto, "decrypt_stream", decrypt)
    data = bytes(range(256)) * 8193
    item = put(vault, tmp_path, data)
    result = storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, tmp_path / "result")
    assert item.size == len(data) + len(b"appended")
    assert result.read_bytes() == data + b"appended"
    assert reads["encrypt"].count(crypto.CHUNK_SIZE) >= 3
    assert reads["decrypt"].count(crypto.CHUNK_SIZE) >= 2


@pytest.mark.parametrize("directory", ["home", "vault_dir", "objects_dir"])
def test_symlink_vault_directories_rejected(vault, tmp_path, directory):
    paths, config, _ = vault
    original = getattr(paths, directory)
    moved = tmp_path / "moved"
    original.rename(moved)
    original.symlink_to(moved, target_is_directory=True)
    with pytest.raises(storage.StorageError):
        storage.load_manifest(paths, KEY, config)


@pytest.mark.parametrize("operation", ["load", "save", "initialize"])
def test_symlink_manifest_rejected(vault, tmp_path, operation):
    paths, config, manifest = vault
    original = paths.manifest_path.read_bytes()
    outside = tmp_path / "outside"
    outside.write_bytes(original)
    paths.manifest_path.unlink()
    paths.manifest_path.symlink_to(outside)
    with pytest.raises(storage.StorageError):
        if operation == "load":
            storage.load_manifest(paths, KEY, config)
        elif operation == "save":
            storage.save_manifest_atomic(paths, KEY, config, manifest)
        else:
            storage.initialize_empty_vault(paths, KEY, config)
    assert outside.read_bytes() == original
    assert paths.manifest_path.is_symlink()


@pytest.mark.parametrize("operation", ["store", "retrieve"])
def test_source_replaced_by_symlink_before_open_rejected(vault, tmp_path, monkeypatch, operation):
    item = put(vault, tmp_path)
    source = tmp_path / "source" if operation == "store" else object_path(vault, item)
    outside = tmp_path / "outside"
    outside.write_bytes(source.read_bytes())
    open_file = os.open
    def substitute(path, flags, *args, **kwargs):
        if Path(path) == source:
            source.unlink()
            source.symlink_to(outside)
        return open_file(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", substitute)
    with pytest.raises(storage.StorageError):
        if operation == "store":
            storage.store_file(vault[0], KEY, vault[1], vault[2], source, "another")
        else:
            storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, tmp_path / "result")
    assert vault[2].entries == [item]
    assert not (tmp_path / "result").exists()
    assert not list(tmp_path.glob(".*.partial"))


def test_uuid_collision_does_not_overwrite_existing_object(vault, tmp_path, monkeypatch):
    item = put(vault, tmp_path)
    path = object_path(vault, item)
    original = path.read_bytes()
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(hex=item.id))
    with pytest.raises(storage.StorageError):
        put(vault, tmp_path, b"different bytes", "another")
    assert path.read_bytes() == original
    assert vault[2].entries == [item]
    assert list(vault[0].objects_dir.iterdir()) == [path]


@pytest.mark.parametrize("operation", ["store", "retrieve", "initialize"])
def test_unsupported_exclusive_publication_fails_closed(vault, tmp_path, monkeypatch, operation):
    item = put(vault, tmp_path)
    before = vault[0].manifest_path.read_bytes()
    def unavailable(*args, **kwargs):
        raise OSError("Hard links unavailable")
    monkeypatch.setattr(os, "link", unavailable)
    with pytest.raises(storage.StorageError):
        if operation == "store":
            put(vault, tmp_path, name="another")
        elif operation == "retrieve":
            storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, tmp_path / "result")
        else:
            paths = resolve_paths(tmp_path / "new")
            storage.initialize_empty_vault(paths, KEY, vault[1])
    if operation == "initialize":
        assert not paths.manifest_path.exists()
        assert not list(paths.vault_dir.glob(".*.tmp"))
    assert vault[0].manifest_path.read_bytes() == before
    assert vault[2].entries == [item]
    assert list(vault[0].objects_dir.iterdir()) == [object_path(vault, item)]
    assert not (tmp_path / "result").exists()
    assert not list(tmp_path.glob(".*.partial"))


def test_initialization_race_does_not_overwrite(vault, tmp_path, monkeypatch):
    paths = resolve_paths(tmp_path / "new")
    link = os.link
    def race(source, destination, **kwargs):
        Path(destination).write_bytes(b"another initializer")
        link(source, destination, **kwargs)
    monkeypatch.setattr(os, "link", race)
    with pytest.raises(storage.StorageError):
        storage.initialize_empty_vault(paths, KEY, vault[1])
    assert paths.manifest_path.read_bytes() == b"another initializer"
    assert not list(paths.vault_dir.glob(".*.tmp"))


@pytest.mark.parametrize("operation", ["load", "retrieve"])
@pytest.mark.parametrize("wrong", ["key", "vault_id"])
def test_wrong_key_or_vault_id_preserves_integrity_error(vault, tmp_path, operation, wrong):
    item = put(vault, tmp_path)
    key = bytes(reversed(KEY)) if wrong == "key" else KEY
    config = AppConfig(vault_id="another-vault") if wrong == "vault_id" else vault[1]
    with pytest.raises(crypto.IntegrityError):
        if operation == "load":
            storage.load_manifest(vault[0], key, config)
        else:
            storage.retrieve_file(vault[0], key, config, vault[2], item.name, tmp_path / "result")
    assert not (tmp_path / "result").exists()
    assert not list(tmp_path.glob(".*.partial"))


@pytest.mark.parametrize("manifest", [None, storage.VaultManifest(1, ()), storage.VaultManifest(1, [None]),
    storage.VaultManifest(1, [entry(id=None)]), storage.VaultManifest(1, [entry(updated_at=None)])])
def test_invalid_in_memory_manifest_rejected_before_write(vault, manifest):
    before = vault[0].manifest_path.read_bytes()
    with pytest.raises(storage.StorageError):
        storage.save_manifest_atomic(vault[0], KEY, vault[1], manifest)
    assert vault[0].manifest_path.read_bytes() == before


@pytest.mark.parametrize("extra", [True, False])
def test_missing_or_extra_entry_fields_rejected(vault, extra):
    item = asdict(entry())
    if extra:
        item["source_path"] = "not allowed"
    else:
        del item["updated_at"]
    write_manifest(vault, {"version": 1, "entries": [item]})
    with pytest.raises(storage.StorageError):
        storage.load_manifest(vault[0], KEY, vault[1])


def test_missing_retrieval_parent_is_controlled(vault, tmp_path):
    item = put(vault, tmp_path)
    with pytest.raises(storage.StorageError):
        storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, tmp_path / "missing" / "result")
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("path", [None, 42, "bad\0path"])
def test_invalid_source_path_is_controlled(vault, path):
    with pytest.raises(storage.StorageError):
        storage.store_file(vault[0], KEY, vault[1], vault[2], path)


def test_architecture_has_no_shell_crypto_duplication_or_later_stage_imports():
    import ast
    tree = ast.parse(Path(storage.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in {
                    "json", "os", "stat", "tempfile", "uuid",
                }
        if isinstance(node, ast.ImportFrom):
            assert node.module in {
                "contextlib", "dataclasses", "datetime", "pathlib", "v2_reference.config", "v2_reference.vault",
            }
            if node.module == "v2_reference.vault":
                assert [alias.name for alias in node.names] == ["crypto"]
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            assert name not in {"eval", "exec", "system", "Popen", "run", "urandom", "AESGCM", "Cipher", "Argon2id", "print"}


def test_changed_source_after_open_rejected_and_descriptor_closed(vault, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"original")
    moved = tmp_path / "moved"
    open_file = os.open
    descriptors = []
    def substitute(path, flags, *args, **kwargs):
        descriptor = open_file(path, flags, *args, **kwargs)
        if Path(path) == source:
            descriptors.append(descriptor)
            source.rename(moved)
            source.symlink_to(moved)
        return descriptor
    monkeypatch.setattr(os, "open", substitute)
    with pytest.raises(storage.StorageError):
        storage.store_file(vault[0], KEY, vault[1], vault[2], source)
    assert descriptors
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    assert vault[2].entries == []
    assert list(vault[0].objects_dir.iterdir()) == []


def test_cleanup_failure_is_controlled_and_does_not_publish_plaintext(vault, tmp_path, monkeypatch):
    item = put(vault, tmp_path)
    path = object_path(vault, item)
    blob = bytearray(path.read_bytes())
    blob[-1] ^= 1
    path.write_bytes(blob)
    unlink = Path.unlink
    def denied(target, *args, **kwargs):
        if target.suffix == ".partial":
            raise PermissionError("cleanup denied")
        return unlink(target, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", denied)
        with pytest.raises(storage.StorageError) as raised:
            storage.retrieve_file(vault[0], KEY, vault[1], vault[2], item.name, tmp_path / "result")
    assert isinstance(raised.value.__cause__, PermissionError)
    assert isinstance(raised.value.__cause__.__context__, crypto.IntegrityError)
    assert not (tmp_path / "result").exists()
    remaining = list(tmp_path.glob(".*.partial"))
    assert len(remaining) == 1 and remaining[0].read_bytes() == b""
    remaining[0].unlink()


def test_store_interruption_cleans_encrypted_staging(vault, tmp_path, monkeypatch):
    def interrupt(source, destination, *args):
        destination.write(b"unfinished encrypted data")
        raise KeyboardInterrupt
    monkeypatch.setattr(crypto, "encrypt_stream", interrupt)
    with pytest.raises(KeyboardInterrupt):
        put(vault, tmp_path)
    assert vault[2].entries == []
    assert list(vault[0].objects_dir.iterdir()) == []


def test_manifest_serialization_rejects_deep_json(vault):
    write_manifest(vault, b"[" * 1200 + b"0" + b"]" * 1200)
    with pytest.raises(storage.StorageError):
        storage.load_manifest(vault[0], KEY, vault[1])
