from pathlib import Path
import errno
import os
import time
import pytest
from relayvault.vault import capsule, store
from relayvault.vault.session import VaultSession, VaultLockedError


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "state"))
    header, key = capsule.metadata("password")
    path = tmp_path / "example.relayvault"
    store.create(path, header, bytes(key))
    key[:] = bytes(len(key))
    return path


def test_real_operations_and_backup_recovery(vault, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"PRIVATE" * 10000)
    with VaultSession.authenticate("password", vault) as session:
        session.store(source, "秘密.txt")
        session.rename("秘密.txt", "renamed")
        assert session.info("renamed")["size"] == len(source.read_bytes())
        target = tmp_path / "retrieved"
        session.retrieve("renamed", target)
        assert target.read_bytes() == source.read_bytes()
        with pytest.raises(store.StorageError):
            session.retrieve("renamed", target)
        session.remove("renamed")
        assert session.list_files() == []
        assert session.verify()["generation"] == 4
    backups = list((tmp_path / "state" / "backups").rglob("*.relayvault"))
    assert len(backups) == 3
    selected = None
    for backup in backups:
        with VaultSession.authenticate("password", backup) as session:
            if session.list_files():
                selected = tmp_path / "recovered.relayvault"
                session.export(selected)
                break
    assert selected.exists()
    with VaultSession.authenticate("password", selected) as recovered:
        assert recovered.list_files()


def test_concurrent_writer_and_external_edits(vault, tmp_path):
    with VaultSession.authenticate("password", vault) as session:
        with pytest.raises(store.ConcurrentWriteError):
            VaultSession.authenticate("password", vault)
        original = vault.read_bytes()
        vault.write_bytes(original)
        source = tmp_path / "source"
        source.write_text("value")
        with pytest.raises(store.ConcurrentWriteError):
            session.store(source)
        assert vault.read_bytes() == original


@pytest.mark.parametrize("phase", ["backup", "write", "sync", "replace"])
def test_prepublication_failure_preserves_original(vault, tmp_path, monkeypatch, phase):
    original = vault.read_bytes()
    source = tmp_path / "source"
    source.write_bytes(b"new")
    with VaultSession.authenticate("password", vault) as session:

        def fail(*a, **k):
            raise OSError(errno.ENOSPC, "injected full disk")

        if phase == "backup":
            monkeypatch.setattr(store, "backup_capsule", fail)
        elif phase == "write":
            monkeypatch.setattr(capsule, "write", fail)
        elif phase == "sync":
            monkeypatch.setattr(os, "fsync", fail)
        else:
            monkeypatch.setattr(os, "replace", fail)
        with pytest.raises(OSError):
            session.store(source)
        assert vault.read_bytes() == original
        assert session.list_files() == []
    assert not list(tmp_path.glob(".relay-*.partial"))


def test_postpublication_failure_is_uncertain_and_locks(vault, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("new")
    with VaultSession.authenticate("password", vault) as session:
        original = store.sync_directory

        def fail_primary(path):
            if path == tmp_path:
                raise OSError("sync failed")
            return original(path)

        monkeypatch.setattr(store, "sync_directory", fail_primary)
        with pytest.raises(store.CommitUncertainError):
            session.store(source)
        assert session.is_locked()
    with VaultSession.authenticate("password", vault) as reopened:
        assert reopened.list_files()[0]["name"] == "source"
        reopened.verify()


def test_symlink_special_and_hardlink_refused(vault, tmp_path):
    alias = tmp_path / "link"
    alias.symlink_to(vault)
    with pytest.raises(store.StorageError):
        store.Store(alias)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(store.StorageError):
        store.open_regular(fifo)
    hard = tmp_path / "hard"
    os.link(vault, hard)
    source = tmp_path / "source"
    source.write_text("new")
    with VaultSession.authenticate("password", vault) as session:
        with pytest.raises(store.StorageError):
            session.store(source)


def test_idle_locks_and_disallows_operations(vault):
    with VaultSession.authenticate("password", vault, timeout=0.01) as session:
        session.start_auto_lock()
        assert session.timed_out.wait(1)
        with pytest.raises(VaultLockedError):
            session.list_files()


@pytest.mark.parametrize("when", ["before", "after"])
def test_disposable_process_interruption_at_publication(vault, tmp_path, when):
    import subprocess
    import sys

    source = tmp_path / "source"
    source.write_text("interrupted payload")
    script = """
import os,sys
from pathlib import Path
from relayvault.vault import store
from relayvault.vault.session import VaultSession
real=store.publish
def interrupted(staged,destination,**kw):
    if destination==Path(sys.argv[1]) and sys.argv[3]=='before': os._exit(77)
    real(staged,destination,**kw)
    if destination==Path(sys.argv[1]): os._exit(77)
store.publish=interrupted
with VaultSession.authenticate('password',sys.argv[1]) as session: session.store(sys.argv[2])
"""
    env = os.environ | {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    process = subprocess.run(
        [sys.executable, "-c", script, str(vault), str(source), when],
        env=env,
        timeout=20,
    )
    assert process.returncode == 77
    with VaultSession.authenticate("password", vault) as reopened:
        assert len(reopened.list_files()) == (0 if when == "before" else 1)
        reopened.verify()
    for temporary in tmp_path.glob(".relay-*.partial"):
        assert b"interrupted payload" not in temporary.read_bytes()
