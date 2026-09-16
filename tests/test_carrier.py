import io
import struct
import zlib
from pathlib import Path
import pytest
from relayvault.vault import capsule, store, png
from relayvault.vault.session import VaultSession
from relayvault.migration import migrate


def image_bytes():
    out = io.BytesIO()
    out.write(png.SIGNATURE)
    png.write_chunk(out, b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png.write_chunk(out, b"IDAT", zlib.compress(b"\0\x12\x34\x56"))
    png.write_chunk(out, b"IEND", b"")
    return out.getvalue()


@pytest.fixture
def carrier(tmp_path, monkeypatch):
    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "state"))
    image = tmp_path / "original.png"
    image.write_bytes(image_bytes())
    header, key = capsule.metadata("password")
    path = tmp_path / "carrier.png"
    store.create(path, header, bytes(key), image=image)
    key[:] = bytes(len(key))
    return path, image


def test_carrier_operations_roundtrip_fresh_home(carrier, tmp_path, monkeypatch):
    path, image = carrier
    original = image.read_bytes()
    source = tmp_path / "secret"
    source.write_bytes(b"private" * 200000)
    with VaultSession.authenticate("password", path) as session:
        session.store(source)
        session.rename("secret", "portable")
        session.verify()
        session.export(tmp_path / "plain.relayvault")
    with path.open("rb") as stream:
        chunks, _ = png.scan(stream)
        preserved = png.SIGNATURE + b"".join(
            capsule.Slice(stream, o, n).read() for o, n, k in chunks if k != png.TYPE
        )
    assert preserved == original == image.read_bytes()
    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "fresh-home"))
    with VaultSession.authenticate("password", path) as session:
        session.retrieve("portable", tmp_path / "recovered")
    assert (tmp_path / "recovered").read_bytes() == source.read_bytes()
    with VaultSession.authenticate(
        "password", tmp_path / "plain.relayvault"
    ) as session:
        session.export(tmp_path / "second.png", image=image)
    with VaultSession.authenticate("password", tmp_path / "second.png") as session:
        session.verify()


def test_segment_reordering_and_stripping(carrier, tmp_path):
    path, _ = carrier
    source = tmp_path / "big"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    with VaultSession.authenticate("password", path) as session:
        session.store(source)
    data = path.read_bytes()
    stream = io.BytesIO(data)
    chunks, _ = png.scan(stream)
    payload = [data[o : o + n] for o, n, k in chunks if k == png.TYPE]
    ordinary = [data[o : o + n] for o, n, k in chunks if k not in {png.TYPE, b"IEND"}]
    reordered = (
        png.SIGNATURE + b"".join(ordinary) + b"".join(reversed(payload)) + data[-12:]
    )
    path.write_bytes(reordered)
    with VaultSession.authenticate("password", path) as session:
        session.verify()
    path.write_bytes(png.SIGNATURE + b"".join(ordinary) + data[-12:])
    with pytest.raises(capsule.FormatError, match="No Relay"):
        store.Store(path)


def test_image_damage_recovery_does_not_bypass_payload_checks(carrier, tmp_path):
    path, _ = carrier
    data = bytearray(path.read_bytes())
    data[45] ^= 1
    path.write_bytes(data)
    with pytest.raises(capsule.FormatError):
        store.Store(path)
    with VaultSession.authenticate("password", path, recovery=True) as session:
        session.export(tmp_path / "rescued.relayvault")
    with VaultSession.authenticate(
        "password", tmp_path / "rescued.relayvault"
    ) as session:
        session.verify()


@pytest.mark.parametrize("damage", ["truncate", "duplicate", "missing", "payload"])
def test_damaged_carriers_refused(carrier, damage):
    path, _ = carrier
    data = path.read_bytes()
    chunks, _ = png.scan(io.BytesIO(data))
    o, n, _ = next(c for c in chunks if c[2] == png.TYPE)
    if damage == "truncate":
        data = data[:-1]
    elif damage == "duplicate":
        data = data[:o] + data[o : o + n] + data[o:]
    elif damage == "missing":
        data = data[:o] + data[o + n :]
    else:
        data = data[: o + 40] + bytes([data[o + 40] ^ 1]) + data[o + 41 :]
    path.write_bytes(data)
    with pytest.raises(ValueError):
        store.Store(path, recovery=True)


def test_creation_rejects_existing_carrier_and_preserves_destination(carrier, tmp_path):
    path, _ = carrier
    header, key = capsule.metadata("new")
    with pytest.raises(capsule.FormatError):
        store.create(tmp_path / "new.png", header, bytes(key), image=path)
    assert not (tmp_path / "new.png").exists()
    original = path.read_bytes()
    with pytest.raises(store.StorageError):
        store.create(path, header, bytes(key))
    assert path.read_bytes() == original


def test_v2_readonly_migration_without_state(tmp_path, monkeypatch):
    from v2_reference import main as old
    from v2_reference.config import resolve_paths
    from v2_reference.vault.session import VaultSession as OldSession
    from v2_reference.config import load_config

    legacy = tmp_path / "v2"
    monkeypatch.setenv("VAULTGAME_HOME", str(legacy))
    monkeypatch.setattr("getpass.getpass", lambda _: "password")
    old._initialize()
    paths = resolve_paths()
    source = tmp_path / "old-secret"
    source.write_bytes(b"legacy content")
    session = OldSession.authenticate("password", load_config(paths), paths)
    session.store(source)
    session.lock()
    paths.state_path.unlink()
    (paths.objects_dir / "orphan.vlt").write_bytes(b"orphan")
    before = {
        p.relative_to(legacy): p.read_bytes() for p in legacy.rglob("*") if p.is_file()
    }
    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "new-state"))
    destination, orphans = migrate(legacy, tmp_path / "migrated.relayvault", "password")
    assert orphans == 1
    assert before == {
        p.relative_to(legacy): p.read_bytes() for p in legacy.rglob("*") if p.is_file()
    }
    with VaultSession.authenticate("password", destination) as restored:
        restored.retrieve("old-secret", tmp_path / "retrieved")
        old_id = load_config(paths).vault_id
        assert restored.store_backend.capsule.header["vault_id"] == old_id
    assert (tmp_path / "retrieved").read_bytes() == b"legacy content"


def test_migration_never_creates_state_inside_source(tmp_path, monkeypatch):
    source = tmp_path / "old"
    source.mkdir()
    monkeypatch.setenv("RELAY_HOME", str(source))
    with pytest.raises(store.StorageError, match="outside"):
        migrate(source, tmp_path / "new.relayvault", "unused")
    assert list(source.iterdir()) == []
