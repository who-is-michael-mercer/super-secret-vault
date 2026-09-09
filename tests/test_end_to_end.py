"""Complete, isolated CLI journeys using the production crypto and storage layers.

Only input, presentation timing, clocks, and explicit failure points are controlled.
Installed-wheel journeys are also verified outside the checkout at release time.
"""

import io
import json
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone

import pytest

from vaultgame import main as app, os_actions, traps
from vaultgame.config import is_initialized, load_config, load_runtime_state, resolve_paths
from vaultgame.terminal import Terminal
from vaultgame.vault import session as session_module, storage
from vaultgame.vault.session import VaultLockedError, VaultSession


PASSWORD = 'RELAY-E2E-PASSWORD-MARKER-91D7'
CONTENT = b'RELAY-E2E-CONTENT-MARKER-61C2'
NAME = 'RELAY-E2E-FILENAME-MARKER.txt'
ROUTE = ['status', 'wake', 'scan', 'probe 13', 'enter null', 'inspect',
         'open black', 'inspect', 'read seal', 'unlock mirror']


@pytest.fixture(autouse=True)
def forbid_machine_actions(monkeypatch):
    """Fail closed even when pytest is invoked without the external audit runner."""
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append((args, kwargs))
        pytest.fail('End-to-end tests must never execute processes or OS actions')

    monkeypatch.setattr(os_actions, 'perform_os_action', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    for name in dir(os):
        if (name in {'system', 'kill', 'killpg', 'popen', 'startfile'}
                or name.startswith(('exec', 'spawn', 'posix_spawn'))):
            if callable(getattr(os, name)):
                monkeypatch.setattr(os, name, forbidden)
    yield
    assert attempts == []


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv('VAULTGAME_HOME', str(tmp_path / 'runtime'))
    return resolve_paths()


def initialize(monkeypatch, answers=(PASSWORD, PASSWORD)):
    replies = iter(answers)
    prompts = []

    def password(prompt):
        prompts.append(prompt)
        try:
            return next(replies)
        except StopIteration:
            pytest.fail('Unexpected initialization password prompt')

    monkeypatch.setattr(app.getpass, 'getpass', password)
    status = app.main(['init'])
    return status, prompts


@pytest.fixture
def vault(home, monkeypatch, capsys):
    status, prompts = initialize(monkeypatch)
    assert status == 0 and len(prompts) == 2
    assert is_initialized(home)
    assert PASSWORD not in capsys.readouterr().out
    config = load_config(home)
    assert config.real_os_actions == {
        'enabled': False, 'allowed_actions': [], 'bindings': {}}
    return home


@pytest.fixture
def sessions(monkeypatch):
    """Observe real sessions and retain their owned buffer only to check cleanup."""
    created = []
    authenticate = VaultSession.authenticate

    def capture(password, config, paths):
        instance = authenticate(password, config, paths)
        created.append((instance, instance._key))
        return instance

    monkeypatch.setattr(VaultSession, 'authenticate', capture)
    yield created
    for instance, buffer in created:
        # Check application cleanup before the fixture's unconditional fallback.
        try:
            assert instance.is_locked()
            assert instance._thread is None
            assert instance._manifest is None and instance._key is None
            assert buffer == bytearray(32)
            with pytest.raises(VaultLockedError):
                instance.list_files()
        finally:
            instance.lock()


def drive(commands, passwords=(), *, terminal=None):
    """Call the real application; callable script steps inspect boundary state."""
    terminal = terminal or Terminal(io.StringIO(), effects=False,
        sleep=lambda _: pytest.fail('Static end-to-end journeys must not sleep'))
    commands, passwords = iter(commands), iter(passwords)
    visits = []

    def read():
        while True:
            try:
                command = next(commands)
            except StopIteration:
                raise EOFError from None
            if callable(command):
                command()
                continue
            if isinstance(command, BaseException):
                raise command
            return command

    def password():
        visits.append(terminal.stream.getvalue())
        try:
            return next(passwords)
        except StopIteration:
            pytest.fail('Unexpected authentication prompt')

    result = app.run_application(terminal=terminal, input_fn=read, password_fn=password)
    output = terminal.stream.getvalue()
    assert PASSWORD not in output
    assert 'Traceback' not in output
    return result, output, visits


def snapshot(paths):
    return {str(path.relative_to(paths.vault_dir)): path.read_bytes()
            for path in paths.vault_dir.rglob('*') if path.is_file()}


def source_file(tmp_path, name='disposable.bin'):
    source = tmp_path / name
    source.write_bytes(CONTENT + bytes(range(256)) * 5000)
    return source


def seed(vault, tmp_path):
    source = source_file(tmp_path)
    result, _, _ = drive(ROUTE + [f'store "{source}" "{NAME}"', 'exit'], [PASSWORD])
    assert result == 0
    return source


def test_successful_lifecycle_lock_replay_and_reauthentication(vault, tmp_path, sessions):
    source = source_file(tmp_path)
    destination = tmp_path / 'retrieved.bin'
    ids = []

    def stored():
        instance = sessions[-1][0]
        entry = instance.list_files()[0]
        ids.append(entry.id)
        assert entry.name == NAME and entry.size == source.stat().st_size

    def renamed():
        instance = sessions[-1][0]
        assert [entry.name for entry in instance.list_files()] == ['renamed.bin']
        with pytest.raises(storage.EntryNotFoundError):
            instance.info(NAME)
        assert instance.list_files()[0].id == ids[0]

    def locked():
        instance, buffer = sessions[0]
        assert instance.is_locked() and buffer == bytearray(32)
        assert instance._manifest is None and instance._thread is None

    result, output, visits = drive(ROUTE + ['list', f'store "{source}" "{NAME}"',
        stored, 'list', f'info "{NAME}"', f'retrieve "{NAME}" "{destination}"',
        f'rename "{NAME}" renamed.bin', renamed, 'list', 'remove renamed.bin', 'yes',
        'list', 'lock', locked, 'unlock mirror'] + ROUTE + ['list', 'exit'],
        [PASSWORD, PASSWORD])
    assert result == 0 and len(visits) == 2
    assert len(sessions) == 2 and sessions[0][0] is not sessions[1][0]
    assert destination.read_bytes() == source.read_bytes()
    assert output.count('PROTECTED INDEX EMPTY.') == 3
    assert 'Name: ' + NAME in output
    assert 'Created:' in output and 'Updated:' in output
    assert 'Unknown command.' in output.split('LINK LOST', 1)[1]
    assert 'relay://sleep>' in output.split('LINK LOST', 1)[1]
    assert all('seal://mirror>' in visit for visit in visits)
    assert 'core://open>' not in visits[0]
    assert all(identity not in output for identity in ids)
    assert list(vault.objects_dir.iterdir()) == []


def test_encrypted_files_persist_but_progress_and_sessions_do_not(vault, tmp_path, sessions):
    source = seed(vault, tmp_path)
    before = snapshot(vault)
    destination = tmp_path / 'after-restart.bin'
    result, output, visits = drive(['unlock mirror', 'status'] + ROUTE +
        ['list', f'retrieve "{NAME}" "{destination}"', 'exit'], [PASSWORD])
    assert result == 0 and len(visits) == 1
    assert output.index('relay://sleep>') < output.index('IDENTITY MATERIAL REQUIRED')
    assert 'Unknown command.' in output and 'CARRIER: ASLEEP' in output
    assert NAME in output and destination.read_bytes() == source.read_bytes()
    assert snapshot(vault) == before
    assert len(sessions) == 2 and sessions[0][0] is not sessions[1][0]
    assert load_runtime_state(vault).cooldown_until is None
    assert json.loads(vault.state_path.read_text()) == {
        'schema_version': 1, 'cooldown_until': None}


def test_decoy_cannot_authenticate_and_back_returns_to_junction(vault):
    before = snapshot(vault)
    result, output, visits = drive(ROUTE[:5] + ['inspect', 'open white', 'status',
        'read index', 'unlock mirror', 'enter null', 'back', 'inspect'])
    assert result == 0 and visits == []
    assert 'ARCHIVE STATUS: PERFECT' in output
    assert 'ERROR COUNT: 0' in output and 'SECURITY STATE: VERIFIED' in output
    assert 'A REAL ARCHIVE WOULD NOT LEAVE THE EXIT OPEN.' in output
    assert output.count('archive://junction>') >= 3
    assert 'IDENTITY MATERIAL REQUIRED' not in output
    assert snapshot(vault) == before


def test_fake_trap_chain_keeps_stored_ciphertext_and_filenames_unchanged(vault, tmp_path):
    seed(vault, tmp_path)
    before = snapshot(vault)
    result, output, visits = drive(['unknown'] * 3 + ['wake', 'probe 03', 'probe 13',
        'enter null', 'open red'])
    assert result == 0 and visits == []
    assert 'RELAY SIGNAL LOST' in output and 'REBUILDING SIGNAL' in output
    assert 'DELETING INDEX_07.SYS' in output and 'PURGE COMPLETE' in output
    assert snapshot(vault) == before


@pytest.fixture
def utc_clock(monkeypatch):
    current = [datetime(2030, 1, 2, tzinfo=timezone.utc)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is not None
            return current[0].astimezone(tz)

    monkeypatch.setattr(app, 'datetime', Clock)
    monkeypatch.setattr(traps, 'datetime', Clock)
    return current


@pytest.mark.parametrize('seconds', [10, 30])
def test_persisted_lockouts_block_restart_until_controlled_expiry(vault, tmp_path,
                                                                 utc_clock, seconds):
    seed(vault, tmp_path)
    before = snapshot(vault)
    wrong = 'WRONG-E2E-PASSWORD-NEVER-PERSIST-3E41'
    commands = ROUTE[:7] + ['unlock wrong'] if seconds == 10 else ROUTE
    result, output, visits = drive(commands, [] if seconds == 10 else [wrong] * 3)
    assert result == (0 if seconds == 10 else 1)
    assert len(visits) == (0 if seconds == 10 else 3)
    assert output.count('IDENTITY REJECTED') == (0 if seconds == 10 else 3)
    assert 'CHECKSUM FAILURE' in output and wrong not in output
    until = datetime.fromisoformat(load_runtime_state(vault).cooldown_until)
    assert until == utc_clock[0] + timedelta(seconds=seconds)
    result, blocked, visits = drive(ROUTE)
    assert result == 0 and visits == []
    assert f'RETRY IN {seconds} SECONDS' in blocked
    assert 'relay://sleep>' not in blocked
    utc_clock[0] += timedelta(seconds=seconds + 1)
    result, restarted, visits = drive(['status'])
    assert result == 0 and visits == [] and 'CARRIER: ASLEEP' in restarted
    assert load_runtime_state(vault).cooldown_until is None
    assert snapshot(vault) == before
    for path in vault.home.rglob('*'):
        if path.is_file():
            assert wrong.encode() not in path.read_bytes()
            assert PASSWORD.encode() not in path.read_bytes()


@pytest.mark.parametrize('failure', ['ciphertext', 'swap', 'destination'])
def test_retrieval_failure_never_publishes_or_keeps_partial_plaintext(vault, tmp_path,
                                                                   sessions, failure):
    source = seed(vault, tmp_path)
    if failure == 'swap':
        other = tmp_path / 'different.bin'
        other.write_bytes(b'Another object with independent AAD')
        assert drive(ROUTE + [f'store "{other}" second.bin', 'exit'], [PASSWORD])[0] == 0
    # Resolve IDs from a real authenticated session, never infer names from disk order.
    with_session = VaultSession.authenticate(PASSWORD, load_config(vault), vault)
    try:
        entries = {entry.name: entry for entry in with_session.list_files()}
    finally:
        with_session.lock()
    target_name = NAME
    original_path = vault.objects_dir / (entries[NAME].id + '.vlt')
    if failure == 'ciphertext':
        corrupted = bytearray(original_path.read_bytes())
        corrupted[18] ^= 1
        original_path.write_bytes(corrupted)
    elif failure == 'swap':
        target_name = 'second.bin'
        (vault.objects_dir / (entries[target_name].id + '.vlt')).write_bytes(
            original_path.read_bytes())
    destination_dir = tmp_path / 'outputs'
    destination_dir.mkdir()
    destination = destination_dir / 'result.bin'
    if failure == 'destination':
        destination.write_bytes(b'EXISTING OUTPUT MUST SURVIVE')
    before = snapshot(vault)
    result, output, _ = drive(ROUTE + [f'retrieve "{target_name}" "{destination}"',
                                     'list', 'exit'], [PASSWORD])
    assert snapshot(vault) == before
    if failure == 'destination':
        assert result == 0 and 'File operation refused' in output
        assert destination.read_bytes() == b'EXISTING OUTPUT MUST SURVIVE'
        assert list(destination_dir.iterdir()) == [destination]
    else:
        assert result == 1 and 'integrity check failed' in output
        assert not destination.exists()
        assert list(destination_dir.iterdir()) == []
    assert 'FILE RETRIEVED' not in output
    assert source.exists()


class ControlledWait:
    """Wake the real watchdog on demand; no elapsed wall-clock sleeps."""
    def __init__(self):
        self.entered = threading.Semaphore(0)
        self.release = threading.Semaphore(0)
        self.stopped = threading.Event()

    def wait(self, interval):
        assert interval > 0
        self.entered.release()
        assert self.release.acquire(timeout=5), 'Watchdog was not released by the test'
        return self.stopped.is_set()

    def clear(self):
        self.stopped.clear()

    def set(self):
        self.stopped.set()
        self.release.release()

    def ready(self):
        assert self.entered.acquire(timeout=5), 'Watchdog did not reach its wait'


@pytest.fixture
def watchdog(monkeypatch, sessions):
    now = [0.0]
    monkeypatch.setattr(session_module.time, 'monotonic', lambda: now[0])
    start = VaultSession.start_auto_lock
    controls = []

    def controlled_start(instance):
        control = ControlledWait()
        instance._stop = control
        controls.append(control)
        start(instance)

    monkeypatch.setattr(VaultSession, 'start_auto_lock', controlled_start)
    return now, controls


def test_watchdog_timeout_discards_stale_input_and_requires_replay(vault, tmp_path,
                                                                 sessions, watchdog):
    now, controls = watchdog
    source = source_file(tmp_path)
    before = snapshot(vault)

    def expire():
        controls[0].ready()
        now[0] = 301
        controls[0].release.release()
        assert sessions[0][0].timed_out.wait(5)

    result, output, visits = drive(ROUTE + [expire, f'store "{source}"',
        'unlock mirror'] + ROUTE + ['list', 'exit'], [PASSWORD, PASSWORD])
    assert result == 0 and len(visits) == 2 and len(sessions) == 2
    assert 'CONNECTION EXPIRED' in output
    reset_output = output.split('CONNECTION EXPIRED', 1)[1]
    assert reset_output.index('relay://sleep>') < reset_output.index('IDENTITY MATERIAL REQUIRED')
    assert 'Unknown command.' in reset_output
    assert 'FILE PROTECTED' not in output and 'PROTECTED INDEX EMPTY' in output
    assert snapshot(vault) == before


def test_busy_real_store_completes_before_later_idle_lock(vault, tmp_path, monkeypatch,
                                                         sessions, watchdog):
    now, controls = watchdog
    source = source_file(tmp_path)
    original_store = storage.store_file

    def controlled_store(*args, **kwargs):
        # This callback runs inside the real session's busy storage operation.
        instance = sessions[0][0]
        assert instance._busy
        controls[0].ready()
        now[0] = 500
        controls[0].release.release()
        controls[0].ready()  # The watchdog has actually rechecked the busy state.
        assert not instance.is_locked()
        return original_store(*args, **kwargs)

    monkeypatch.setattr(storage, 'store_file', controlled_store)

    def after_store():
        instance = sessions[0][0]
        assert not instance._busy and instance._last_activity == 500
        assert not instance.is_locked()
        controls[0].release.release()
        controls[0].ready()  # Long operation refreshed activity, so no immediate lock.
        assert not instance.is_locked()
        now[0] = 801
        controls[0].release.release()
        assert instance.timed_out.wait(5)

    destination = tmp_path / 'after-busy.bin'
    result, output, visits = drive(ROUTE + [f'store "{source}"', after_store,
        'remove disposable.bin'] + ROUTE +
        [f'retrieve disposable.bin "{destination}"', 'exit'], [PASSWORD, PASSWORD])
    assert result == 0 and len(visits) == 2
    assert 'FILE PROTECTED' in output and 'CONNECTION EXPIRED' in output
    assert destination.read_bytes() == source.read_bytes()
    assert "remove 'disposable.bin'?" not in output


@pytest.mark.parametrize('unlocked', [False, True])
@pytest.mark.parametrize('interrupt', [KeyboardInterrupt, EOFError])
def test_interrupts_restore_terminal_and_clean_sessions(vault, tmp_path, sessions,
                                                       unlocked, interrupt):
    seed(vault, tmp_path)
    before = snapshot(vault)

    class TTY(io.StringIO):
        def isatty(self):
            return True

    terminal = Terminal(TTY(), effects=True, sleep=lambda _: None)
    commands = (ROUTE if unlocked else []) + [interrupt()]
    result, output, _ = drive(commands, [PASSWORD] if unlocked else [], terminal=terminal)
    assert result == 0 and 'RELAY DISCONNECTED' in output
    assert '\x1b[0m\x1b[?25h' in output
    assert output.rfind('\x1b[?25h') > output.rfind('\x1b[?25l')
    assert snapshot(vault) == before


def test_shell_looking_game_and_vault_inputs_are_inert(vault):
    before = snapshot(vault)
    result, output, visits = drive(['wake', 'probe "$(reboot)"', 'probe 13',
        'enter null', 'open "red; shutdown -h now"', 'open black', 'read seal',
        'unlock mirror', 'store "/tmp/file; rm -rf /"', 'info "| cat /etc/passwd"',
        'list > /tmp/relay-e2e-injection', 'list', 'exit'], [PASSWORD])
    assert result == 0 and len(visits) == 1
    assert 'Unknown command' in output and 'File operation refused' in output
    assert 'PROTECTED INDEX EMPTY' in output
    assert snapshot(vault) == before


def test_password_content_and_filename_markers_never_leak_to_persisted_vault(vault,
                                                                          tmp_path,
                                                                          sessions):
    seed(vault, tmp_path)
    config = load_config(vault)
    instance = VaultSession.authenticate(PASSWORD, config, vault)
    try:
        key = bytes(instance._key)
        identity = instance.list_files()[0].id
    finally:
        instance.lock()
    for path in vault.home.rglob('*'):
        assert NAME not in path.name
        if path.is_file():
            contents = path.read_bytes()
            assert PASSWORD.encode() not in contents
            assert key not in contents
            assert CONTENT not in contents
            assert NAME.encode() not in contents
    assert [path.name for path in vault.objects_dir.iterdir()] == [identity + '.vlt']
    assert vault.manifest_path.read_bytes().startswith(b'RVLT')


@pytest.mark.parametrize('answers', [('', ''), ('mismatch-one', 'mismatch-two')])
def test_init_rejects_empty_or_mismatched_password_without_completion(home, monkeypatch,
                                                                   capsys, answers):
    status, prompts = initialize(monkeypatch, answers)
    assert status == 1 and len(prompts) == 2
    assert not is_initialized(home)
    assert not home.config_path.exists() and not home.manifest_path.exists()
    assert not home.state_path.exists()
    output = capsys.readouterr()
    for answer in answers:
        if answer:
            assert answer not in output.out + output.err


def test_reinitialization_preserves_existing_vault_and_authentication(vault, tmp_path,
                                                                    monkeypatch, sessions):
    seed(vault, tmp_path)
    before = snapshot(vault)
    config_bytes, state_bytes = vault.config_path.read_bytes(), vault.state_path.read_bytes()
    status, prompts = initialize(monkeypatch, ())
    assert status == 1 and prompts == []
    assert snapshot(vault) == before
    assert vault.config_path.read_bytes() == config_bytes
    assert vault.state_path.read_bytes() == state_bytes
    assert drive(ROUTE + ['list', 'exit'], [PASSWORD])[0] == 0


def test_partial_init_failure_preserves_foreign_data_and_allows_safe_retry(home,
                                                                        monkeypatch):
    home.home.mkdir()
    unrelated = home.home / 'existing-disposable-note.txt'
    unrelated.write_bytes(b'Never remove unrelated existing data')
    writer = app.save_runtime_state_atomic

    def fail_state(*args, **kwargs):
        raise OSError('Injected final initialization write failure')

    monkeypatch.setattr(app, 'save_runtime_state_atomic', fail_state)
    assert initialize(monkeypatch)[0] == 1
    assert unrelated.read_bytes() == b'Never remove unrelated existing data'
    assert not is_initialized(home)
    assert not home.config_path.exists() and not home.manifest_path.exists()
    assert list(home.objects_dir.iterdir()) == []
    assert not list(home.home.rglob('*.partial'))
    monkeypatch.setattr(app, 'save_runtime_state_atomic', writer)
    assert initialize(monkeypatch)[0] == 0
    assert drive(ROUTE + ['list', 'exit'], [PASSWORD])[0] == 0
    assert unrelated.exists()
