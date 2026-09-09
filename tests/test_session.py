import base64

from vaultgame.config import AppConfig, resolve_paths
from vaultgame.vault import crypto, storage
from vaultgame.vault.session import VaultSession


def test_authentication_and_lock(tmp_path):
    kdf = dict(salt=base64.b64encode(bytes(range(16))).decode(), iterations=3,
               memory_kib=65536, lanes=4, length=32)
    key = crypto.derive_master_key('disposable-password', kdf)
    config = AppConfig(vault_id='test-vault', kdf=kdf,
        encryption={'algorithm': 'AES-256-GCM', 'format_version': 1},
        key_check=crypto.create_key_check(key, 'test-vault'), auto_lock_seconds=300)
    paths = resolve_paths(tmp_path)
    storage.initialize_empty_vault(paths, key, config)
    session = VaultSession.authenticate('disposable-password', config, paths)
    assert not session.is_locked()
    assert session.list_files() == []
    session.lock()
    assert session.is_locked()

import copy
import threading
from pathlib import Path

import pytest

from vaultgame.config import ConfigError
from vaultgame.vault import session as session_module
from vaultgame.vault.session import AuthenticationError, VaultLockedError


@pytest.fixture(scope='module')
def credentials():
    password = 'Session-Disposable-秘密-é'
    kdf = dict(salt=base64.b64encode(bytes(range(16))).decode(), iterations=3,
               memory_kib=65536, lanes=4, length=32)
    key = crypto.derive_master_key(password, kdf)
    config = AppConfig(vault_id='session-test-vault', kdf=kdf,
        encryption={'algorithm': 'AES-256-GCM', 'format_version': 1},
        key_check=crypto.create_key_check(key, 'session-test-vault'), auto_lock_seconds=300)
    return password, key, config


@pytest.fixture
def vault(tmp_path, credentials):
    password, key, template = credentials
    config = copy.deepcopy(template)
    paths = resolve_paths(tmp_path / 'vault-home')
    storage.initialize_empty_vault(paths, key, config)
    return password, key, config, paths


@pytest.fixture
def unlocked(vault):
    password, _, config, paths = vault
    session = VaultSession.authenticate(password, config, paths)
    yield session
    session.lock()


def snapshot(paths):
    return {str(p.relative_to(paths.home)): p.read_bytes()
            for p in paths.home.rglob('*') if p.is_file()}


@pytest.mark.parametrize('change', ['wrong_password', 'changed_password', 'vault_id',
                                     'nonce', 'ciphertext', 'tag'])
def test_authentication_failure(vault, change):
    password, _, config, paths = vault
    if change == 'wrong_password':
        password = 'wrong'
    elif change == 'changed_password':
        password += ' '
    elif change == 'vault_id':
        config.vault_id += '-other'
    else:
        field = 'nonce' if change == 'nonce' else 'ciphertext'
        data = bytearray(base64.b64decode(config.key_check[field]))
        data[-1 if change == 'tag' else 0] ^= 1
        config.key_check[field] = base64.b64encode(data).decode()
    with pytest.raises(AuthenticationError):
        VaultSession.authenticate(password, config, paths)


@pytest.mark.parametrize('change, error', [('tag', crypto.IntegrityError),
    ('header', crypto.VaultFormatError), ('missing', storage.StorageError)])
def test_manifest_damage_after_valid_keycheck_is_not_wrong_password(vault, change, error):
    password, _, config, paths = vault
    if change == 'missing':
        paths.manifest_path.unlink()
    else:
        blob = bytearray(paths.manifest_path.read_bytes())
        blob[-1 if change == 'tag' else 0] ^= 1
        paths.manifest_path.write_bytes(blob)
    with pytest.raises(error) as caught:
        VaultSession.authenticate(password, config, paths)
    assert not isinstance(caught.value, AuthenticationError)


def test_incomplete_config_rejected_before_derivation(vault, monkeypatch):
    def forbidden(*args):
        pytest.fail('Incomplete configuration reached Argon2')
    monkeypatch.setattr(crypto, 'derive_master_key', forbidden)
    with pytest.raises(ConfigError):
        VaultSession.authenticate('unused', AppConfig(), vault[3])


def test_lock_clears_owned_key_manifest_and_preserves_storage(unlocked, vault):
    original = snapshot(vault[3])
    buffer = unlocked._key
    assert any(buffer)
    assert not any(value == vault[0] for value in vars(unlocked).values())
    unlocked.lock()
    unlocked.lock()
    assert buffer == bytearray(32)
    assert unlocked._key is None
    assert unlocked._manifest is None
    assert snapshot(vault[3]) == original


@pytest.mark.parametrize('method, arguments', [
    ('list_files', ()), ('info', ('name',)), ('store', ('source',)),
    ('retrieve', ('name', 'destination')), ('remove', ('name',)),
    ('rename', ('old', 'new')), ('touch_activity', ()), ('start_auto_lock', ())])
def test_locked_operations_rejected(unlocked, method, arguments):
    unlocked.lock()
    with pytest.raises(VaultLockedError):
        getattr(unlocked, method)(*arguments)
    assert unlocked.is_locked()


def test_real_session_lifecycle(unlocked, tmp_path, vault, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(session_module.time, 'monotonic', lambda: clock[0])
    source = tmp_path / 'source.txt'
    data = b'SESSION-DISPOSABLE-CONTENT\x00' * 50000
    source.write_bytes(data)
    entry = unlocked.store(source, 'My Notes.txt')
    assert unlocked._last_activity == 100
    assert not unlocked._busy
    assert [e.name for e in unlocked.list_files()] == ['My Notes.txt']
    info = unlocked.info('My Notes.txt')
    assert set(info) == {'name', 'size', 'created_at', 'updated_at'}
    assert info['size'] == len(data)
    output = unlocked.retrieve('My Notes.txt', tmp_path / 'output')
    assert output.read_bytes() == data
    object_path = vault[3].objects_dir / f'{entry.id}.vlt'
    encrypted = object_path.read_bytes()
    clock[0] = 200
    renamed = unlocked.rename('My Notes.txt', 'Renamed.txt')
    assert renamed.id == entry.id
    assert renamed.created_at == entry.created_at
    assert object_path.read_bytes() == encrypted
    assert unlocked._last_activity == 200
    unlocked.remove('Renamed.txt')
    assert unlocked.list_files() == []
    assert not object_path.exists()
    assert not unlocked.is_locked()


@pytest.mark.parametrize('method, function, arguments', [
    ('store', 'store_file', ('unused',)), ('retrieve', 'retrieve_file', ('n', 'd')),
    ('remove', 'remove_file', ('n',)), ('rename', 'rename_file', ('n', 'm'))])
def test_storage_failures_clear_busy_and_keep_session_usable(unlocked, monkeypatch,
                                                            method, function, arguments):
    def fail(*args):
        assert unlocked._busy
        raise storage.StorageError('simulated I/O failure')
    monkeypatch.setattr(storage, function, fail)
    with pytest.raises(storage.StorageError):
        getattr(unlocked, method)(*arguments)
    assert not unlocked._busy
    assert not unlocked.is_locked()
    assert unlocked.list_files() == []


def test_remove_postcommit_unlink_failure_keeps_manifest_consistent(unlocked, tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.write_bytes(b'synthetic')
    entry = unlocked.store(source)
    object_path = unlocked.paths.objects_dir / f'{entry.id}.vlt'
    unlink = Path.unlink
    def fail_object(path, *args, **kwargs):
        if path == object_path:
            raise OSError('unlink denied')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail_object)
    with pytest.raises(storage.StorageError):
        unlocked.remove('source')
    assert unlocked.list_files() == []
    assert storage.load_manifest(unlocked.paths, bytes(unlocked._key), unlocked.config).entries == []
    assert object_path.exists()


def test_store_failed_manifest_commit_does_not_change_session_manifest(unlocked, tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.write_bytes(b'synthetic')
    original = unlocked.paths.manifest_path.read_bytes()
    def fail(*args):
        raise storage.StorageError('manifest failed')
    monkeypatch.setattr(storage, 'save_manifest_atomic', fail)
    with pytest.raises(storage.StorageError):
        unlocked.store(source)
    assert unlocked.list_files() == []
    assert unlocked.paths.manifest_path.read_bytes() == original


def test_session_retrieval_preserves_integrity_failure_cleanup(unlocked, tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'synthetic')
    entry = unlocked.store(source)
    object_path = unlocked.paths.objects_dir / f'{entry.id}.vlt'
    blob = bytearray(object_path.read_bytes())
    blob[-1] ^= 1
    object_path.write_bytes(blob)
    destination = tmp_path / 'output'
    with pytest.raises(crypto.IntegrityError):
        unlocked.retrieve('source', destination)
    assert not destination.exists()
    assert not list(tmp_path.glob('*.partial'))
    assert not unlocked._busy


class ControlledWait:
    """Drive watchdog checks explicitly without a wall-clock timeout dependency."""
    def __init__(self):
        self.entered = threading.Semaphore(0)
        self.release = threading.Semaphore(0)
        self.stopped = False

    def wait(self, interval):
        assert interval > 0
        self.entered.release()
        assert self.release.acquire(timeout=3), 'watchdog did not get a test wakeup'
        return self.stopped

    def set(self):
        self.stopped = True
        self.release.release()

    def clear(self):
        self.stopped = False

    def cycle(self):
        assert self.entered.acquire(timeout=3), 'watchdog never started waiting'
        self.release.release()


@pytest.fixture
def watchdog(unlocked, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(session_module.time, 'monotonic', lambda: now[0])
    unlocked.touch_activity()
    control = ControlledWait()
    unlocked._stop = control
    return unlocked, now, control


def test_idle_watchdog_clears_access_and_stops(watchdog):
    session, now, control = watchdog
    buffer = session._key
    session.start_auto_lock()
    thread = session._thread
    now[0] = 301
    control.cycle()
    assert session.timed_out.wait(3)
    thread.join(3)
    assert not thread.is_alive()
    assert session.is_locked()
    assert buffer == bytearray(32)
    assert session._manifest is None
    with pytest.raises(VaultLockedError):
        session.list_files()


def test_activity_postpones_timeout(watchdog):
    session, now, control = watchdog
    session.start_auto_lock()
    now[0] = 299
    session.touch_activity()
    now[0] = 301
    control.cycle()
    assert control.entered.acquire(timeout=3)
    assert not session.is_locked()
    now[0] = 600
    control.release.release()
    assert session.timed_out.wait(3)


@pytest.mark.parametrize('method, function, arguments', [
    ('store', 'store_file', ('unused',)), ('retrieve', 'retrieve_file', ('n', 'd')),
    ('remove', 'remove_file', ('n',)), ('rename', 'rename_file', ('n', 'm'))])
def test_busy_operation_prevents_timeout_and_refreshes_activity(watchdog, monkeypatch,
                                                              method, function, arguments):
    session, now, control = watchdog
    started, finish = threading.Event(), threading.Event()
    errors = []
    def work(*args):
        started.set()
        assert finish.wait(3)
    monkeypatch.setattr(storage, function, work)
    def run():
        try:
            getattr(session, method)(*arguments)
        except BaseException as error:
            errors.append(error)
    operation = threading.Thread(target=run)
    session.start_auto_lock()
    operation.start()
    try:
        assert started.wait(3)
        now[0] = 500
        control.cycle()
        assert control.entered.acquire(timeout=3)
        assert not session.is_locked()
        finish.set()
        operation.join(3)
        assert not errors
        assert not operation.is_alive()
        assert not session._busy
        assert session._last_activity == 500
        control.release.release()
        assert control.entered.acquire(timeout=3)
        assert not session.is_locked()
        now[0] = 801
        control.release.release()
        assert session.timed_out.wait(3)
    finally:
        finish.set()
        operation.join(3)


@pytest.mark.parametrize('stop_method', ['stop_auto_lock', 'lock'])
def test_watchdog_start_idempotent_and_cleanup(watchdog, stop_method):
    session, _, control = watchdog
    session.start_auto_lock()
    first = session._thread
    assert control.entered.acquire(timeout=3)
    session.start_auto_lock()
    assert session._thread is first
    getattr(session, stop_method)()
    assert not first.is_alive()
    assert session._thread is None
    assert session.is_locked() == (stop_method == 'lock')
    session.stop_auto_lock()


def test_manual_lock_during_io_is_immediate_and_never_revives(unlocked, monkeypatch):
    started, finish = threading.Event(), threading.Event()
    errors = []
    def work(*args):
        started.set()
        assert finish.wait(3)
    monkeypatch.setattr(storage, 'store_file', work)
    def run():
        try:
            unlocked.store('unused')
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert started.wait(3)
        buffer = unlocked._key
        unlocked.lock()
        assert unlocked.is_locked()
        assert buffer == bytearray(32)
        with pytest.raises(VaultLockedError):
            unlocked.info('name')
    finally:
        finish.set()
        thread.join(3)
    assert not errors
    assert not thread.is_alive()
    assert unlocked._manifest is None
    assert unlocked._key is None
    assert not unlocked._busy


def test_stop_then_restart_watchdog(watchdog):
    session, now, control = watchdog
    session.start_auto_lock()
    first = session._thread
    assert control.entered.acquire(timeout=3)
    session.stop_auto_lock()
    assert not first.is_alive()
    session.start_auto_lock()
    second = session._thread
    assert second is not first
    now[0] = 301
    control.cycle()
    assert session.timed_out.wait(3)
    session.stop_auto_lock()
    assert not second.is_alive()


def test_overlapping_mutations_are_serialized(unlocked, monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    second_attempted = threading.Event()
    calls, errors = [], []
    def work(paths, key, config, manifest, source, name):
        calls.append(source)
        if source == 'first':
            entered.set()
            assert finish.wait(3)
    monkeypatch.setattr(storage, 'store_file', work)
    def run(source):
        try:
            if source == 'second':
                second_attempted.set()
            unlocked.store(source)
        except BaseException as error:
            errors.append(error)
    first = threading.Thread(target=run, args=('first',))
    second = threading.Thread(target=run, args=('second',))
    first.start()
    try:
        assert entered.wait(3)
        second.start()
        assert second_attempted.wait(3)
        assert calls == ['first']
    finally:
        finish.set()
        first.join(3)
        second.join(3)
    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert calls == ['first', 'second']


def test_interrupted_storage_clears_busy(unlocked, monkeypatch):
    def interrupt(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(storage, 'store_file', interrupt)
    with pytest.raises(KeyboardInterrupt):
        unlocked.store('unused')
    assert not unlocked._busy
    assert not unlocked.is_locked()


def test_timeout_uses_configuration(watchdog):
    session, now, control = watchdog
    session.config.auto_lock_seconds = 0.5
    session.start_auto_lock()
    now[0] = 0.5
    control.cycle()
    assert session.timed_out.wait(3)


def test_authentication_never_constructs_session_when_verifier_fails(vault, monkeypatch):
    def forbidden(*args):
        pytest.fail('Half-authenticated session was constructed')
    monkeypatch.setattr(VaultSession, '__init__', forbidden)
    with pytest.raises(AuthenticationError):
        VaultSession.authenticate('incorrect', vault[2], vault[3])


def test_session_architecture_is_separate():
    import ast
    tree = ast.parse(Path(session_module.__file__).read_text())
    forbidden = {'game', 'levels', 'traps', 'os_actions', 'terminal', 'parser',
                 'subprocess', 'socket', 'requests'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(set(alias.name.split('.')) & forbidden for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert not set((node.module or '').split('.')) & forbidden
            assert not any(alias.name in forbidden for alias in node.names)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
            assert name not in {'eval', 'exec', 'system', 'print'}
