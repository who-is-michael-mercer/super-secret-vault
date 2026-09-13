"""Stage 10 application integration with isolated data and inert input."""

import base64
import copy
import io
from datetime import datetime, timedelta, timezone

import pytest

from v2_reference import main as app
from v2_reference.config import (AppConfig, RuntimeState, load_runtime_state,
                              resolve_paths, save_config_atomic,
                              save_runtime_state_atomic)
from v2_reference.terminal import Terminal
from v2_reference.vault import crypto, storage
from v2_reference.vault.session import VaultSession


def test_uninitialized_startup_never_prompts(tmp_path, monkeypatch):
    monkeypatch.setenv('VAULTGAME_HOME', str(tmp_path / 'absent'))
    output = io.StringIO()
    def forbidden(*args):
        raise AssertionError('Startup must not prompt before initialization')
    assert app.run_application(terminal=Terminal(output, effects=False),
                               input_fn=forbidden, password_fn=forbidden) == 0
    assert 'relay init' in output.getvalue()
    assert not (tmp_path / 'absent').exists()


ROUTE = ['connect bus', 'scan', 'route -n', 'probe 13', 'connect 13',
         'mount archive0', 'mount black', 'cat controller', 'connect sealctl',
         'sealctl status', 'sealctl unlock']


@pytest.fixture(scope='module')
def credentials():
    password = 'Stage10-disposable-秘密-7F29'
    kdf = dict(salt=base64.b64encode(bytes(range(16))).decode(), iterations=3,
               memory_kib=65536, lanes=4, length=32)
    key = crypto.derive_master_key(password, kdf)
    config = AppConfig(vault_id='integration-test-vault', kdf=kdf,
        encryption={'algorithm': 'AES-256-GCM', 'format_version': 1},
        key_check=crypto.create_key_check(key, 'integration-test-vault'),
        auto_lock_seconds=300, traps={'enabled': True, 'disabled_traps': []},
        real_os_actions={'enabled': False, 'allowed_actions': [], 'bindings': {}})
    return password, key, config


@pytest.fixture
def vault(tmp_path, monkeypatch, credentials):
    password, key, template = credentials
    config = copy.deepcopy(template)
    paths = resolve_paths(tmp_path / 'runtime')
    storage.initialize_empty_vault(paths, key, config)
    save_config_atomic(paths, config)
    save_runtime_state_atomic(paths, RuntimeState())
    monkeypatch.setenv('VAULTGAME_HOME', str(paths.home))
    # Fail closed even when this module is run without the outer audit runner.
    from v2_reference import os_actions
    def forbidden(*args, **kwargs):
        pytest.fail('Real OS action attempted')
    monkeypatch.setattr(os_actions, 'perform_os_action', forbidden)
    return password, key, config, paths


def drive(commands, passwords=(), *, input_hook=None, terminal=None):
    output = io.StringIO() if terminal is None else terminal.stream
    terminal = Terminal(output, effects=False) if terminal is None else terminal
    commands, passwords = iter(commands), iter(passwords)
    visits = []
    def read(prompt=''):
        try:
            command = next(commands)
        except StopIteration:
            raise EOFError from None
        if input_hook is not None:
            input_hook(command)
        if isinstance(command, BaseException):
            raise command
        return command
    def password(prompt=''):
        visits.append(output.getvalue())
        try:
            value = next(passwords)
        except StopIteration:
            pytest.fail('Unexpected password prompt')
        if isinstance(value, BaseException):
            raise value
        return value
    result = app.run_application(terminal=terminal, input_fn=read, password_fn=password)
    return result, output.getvalue(), visits


def test_correct_route_unlocks_and_exits(vault):
    password, _, _, _ = vault
    result, output, visits = drive(ROUTE + ['exit'], [password])
    assert result == 0
    assert len(visits) == 1
    assert 'sealctl:/control>' in visits[0]
    assert 'auth: identity material required' in visits[0]
    assert 'vault0:/data>' not in visits[0]
    assert 'vault0:/data>' in output
    assert 'relay0: carrier detected' in output
    assert '03  closed' in output
    assert password not in output


def test_vault_operations_and_manual_lock(vault, tmp_path):
    password, key, config, paths = vault
    source = tmp_path / 'My Source.bin'
    source.write_bytes(b'Unique integration bytes\x00\xff')
    destination = tmp_path / 'retrieved.bin'
    commands = ROUTE + ['list', f'store "{source}" "My Notes.txt"', 'list',
        'info "My Notes.txt"', f'retrieve "My Notes.txt" "{destination}"',
        'rename "My Notes.txt" "Renamed Notes.txt"', 'remove "Renamed Notes.txt"',
        'yes', 'lock', 'help']
    result, output, _ = drive(commands, [password])
    assert result == 0
    assert destination.read_bytes() == source.read_bytes()
    assert storage.load_manifest(paths, key, config).entries == []
    assert not list(paths.objects_dir.iterdir())
    assert 'My Notes.txt' in output
    assert 'created:' in output and 'updated:' in output
    assert 'session: locked' in output
    assert output.count('relay0:/proc/relay>') >= 3
    assert 'auth: identity material required' not in output.rsplit('session: locked', 1)[1]


@pytest.mark.parametrize('active', [True, False])
def test_startup_cooldown(vault, active):
    _, _, _, paths = vault
    until = datetime.now(timezone.utc) + timedelta(seconds=60 if active else -60)
    save_runtime_state_atomic(paths, RuntimeState(cooldown_until=until.isoformat()))
    result, output, visits = drive(['status'])
    assert result == 0
    assert visits == []
    if active:
        assert 'relay0: backoff' in output
        assert 'relay0:/proc/relay>' not in output
        assert load_runtime_state(paths).cooldown_until == until.isoformat()
    else:
        assert 'relay0: carrier detected' in output
        assert load_runtime_state(paths).cooldown_until is None


@pytest.fixture
def sessions(monkeypatch):
    created = []
    authenticate = VaultSession.authenticate
    def capture(password, config, paths):
        session = authenticate(password, config, paths)
        created.append(session)
        return session
    monkeypatch.setattr(VaultSession, 'authenticate', capture)
    yield created
    for session in created:
        session.lock()
        assert session._thread is None


def test_timeout_while_reading_ignores_command_and_resets(vault, sessions, monkeypatch):
    import threading
    from v2_reference.vault import session as session_module
    password, key, config, paths = vault
    clock = [0.0]
    monkeypatch.setattr(session_module.time, 'monotonic', lambda: clock[0])
    wake = threading.Event()
    started = threading.Event()
    original_start = VaultSession.start_auto_lock
    def start(session):
        wait = session._stop.wait
        def controlled_wait(interval):
            started.set()
            assert wake.wait(3), 'test must wake watchdog'
            return wait(0)
        monkeypatch.setattr(session._stop, 'wait', controlled_wait)
        original_start(session)
    monkeypatch.setattr(VaultSession, 'start_auto_lock', start)
    calls = []
    monkeypatch.setattr(VaultSession, 'store', lambda *args: calls.append(args))
    before = paths.manifest_path.read_bytes()
    def expire(command):
        if command == 'store ignored':
            assert started.wait(3)
            clock[0] = 301
            wake.set()
            assert sessions[0].timed_out.wait(3)
    result, output, _ = drive(ROUTE + ['store ignored', 'help'], [password], input_hook=expire)
    assert result == 0
    assert calls == []
    assert sessions[0].is_locked()
    assert sessions[0]._key is None
    assert 'session: locked (idle timeout)' in output
    assert 'relay0:/proc/relay>' in output.split('session: locked (idle timeout)')[1]
    assert paths.manifest_path.read_bytes() == before


def vault_snapshot(paths):
    return {str(path.relative_to(paths.vault_dir)): path.read_bytes()
            for path in paths.vault_dir.rglob('*') if path.is_file()}


@pytest.mark.parametrize('commands, clue, exits, cooldown', [
    (['unknown', 'unknown', 'unknown'], 'relay0: carrier degraded', False, 0),
    (ROUTE[:3] + ['probe 03'], 'route: recovering', False, 0),
    (ROUTE[:3] + ['probe 08'], 'route: recovering', False, 0),
    (ROUTE[:6] + ['mount white', 'status', 'cat index'],
     'records: 2', False, 0),
    (ROUTE[:6] + ['mount red', 'mount -o rw red'], 'red: journal detached', True, 0),
    (ROUTE[:9] + ['sealctl wrong'], 'metadata mismatch', True, 10),
])
def test_wrong_paths_use_fake_traps_without_vault_mutation(vault, commands, clue, exits, cooldown):
    _, key, config, paths = vault
    source = paths.home.parent / 'protected.txt'
    source.write_bytes(b'protected fake-trap regression content')
    manifest = storage.load_manifest(paths, key, config)
    storage.store_file(paths, key, config, manifest, source)
    before = vault_snapshot(paths)
    before_time = datetime.now(timezone.utc)
    result, output, visits = drive(commands)
    assert result == 0
    assert clue in output
    assert visits == []
    assert vault_snapshot(paths) == before
    assert ('relay0: disconnected' not in output) == exits
    state = load_runtime_state(paths)
    if cooldown:
        duration = (datetime.fromisoformat(state.cooldown_until) - before_time).total_seconds()
        assert cooldown <= duration < cooldown + 3
    else:
        assert state.cooldown_until is None
    for hidden in ['false_probe', 'signal_scramble', 'seal_lockout', 'red_purge',
                   manifest.entries[0].id, 'route_verified', 'seal_ready']:
        assert hidden not in output


def test_probe_trap_clears_discovery(vault):
    commands = ROUTE[:4] + ['probe 03', 'connect 13', 'help']
    _, output, visits = drive(commands)
    assert visits == []
    assert 'archive0:/mnt>' not in output
    assert 'command: unavailable' in output


def test_one_bad_password_then_success_and_visit_counter_reset(vault, sessions):
    password, _, _, paths = vault
    result, output, visits = drive(ROUTE + ['lock'] + ROUTE + ['exit'],
                                  ['bad', 'bad', password, 'bad', 'bad', password])
    assert result == 0
    assert len(visits) == 6
    assert output.count('auth: key check failed') == 4
    assert len(sessions) == 2
    assert all(session.is_locked() for session in sessions)
    assert load_runtime_state(paths).cooldown_until is None


def test_three_bad_passwords_persist_lockout_and_exit(vault):
    _, _, _, paths = vault
    now = datetime.now(timezone.utc)
    result, output, visits = drive(ROUTE + ['list'], ['bad', 'bad', 'bad'])
    assert result == 1
    assert len(visits) == 3
    assert output.count('auth: key check failed') == 3
    assert 'vault0:/data>' not in output
    until = datetime.fromisoformat(load_runtime_state(paths).cooldown_until)
    assert 30 <= (until - now).total_seconds() < 33
    assert 'archive0: metadata mismatch' in output
    result, output, _ = drive(ROUTE)
    assert result == 0 and 'relay0: backoff' in output
    assert 'relay0:/proc/relay>' not in output


def test_disabled_auth_trap_does_not_allow_fourth_password(vault):
    _, _, config, paths = vault
    config.traps['enabled'] = False
    save_config_atomic(paths, config)
    result, output, visits = drive(ROUTE, ['bad', 'bad', 'bad'])
    assert result == 1
    assert len(visits) == 3
    assert 'metadata mismatch' not in output
    assert load_runtime_state(paths).cooldown_until is None


@pytest.mark.parametrize('damage', ['tag', 'header', 'json'])
def test_corrupt_manifest_is_not_wrong_password(vault, sessions, damage):
    password, key, config, paths = vault
    blob = bytearray(paths.manifest_path.read_bytes())
    if damage == 'json':
        blob = crypto.encrypt_bytes(b'not json', key,
            crypto.build_aad(config.vault_id, 'manifest'), crypto.MANIFEST)
    else:
        blob[-1 if damage == 'tag' else 0] ^= 1
    paths.manifest_path.write_bytes(blob)
    result, output, visits = drive(ROUTE, [password])
    assert result == 1 and len(visits) == 1
    assert 'auth: key check failed' not in output
    assert 'vault0:/data>' not in output
    assert 'Traceback' not in output
    assert sessions == []
    assert password not in output


@pytest.mark.parametrize('command', [
    'store', 'store a b c', 'retrieve', 'retrieve a', 'retrieve a b c',
    'remove', 'remove a b', 'rename', 'rename a', 'rename a b c', 'info', 'info a b',
    'list a', 'help a', 'clear a', 'lock a', 'exit a',
])
def test_argument_errors_keep_vault_usable_without_mutation(vault, sessions, command):
    password, _, _, paths = vault
    before = vault_snapshot(paths)
    result, output, _ = drive(ROUTE + [command, 'list', 'exit'], [password])
    assert result == 0
    assert 'usage:' in output
    assert 'index: empty' in output
    assert vault_snapshot(paths) == before


@pytest.mark.parametrize('answer, removed', [('', False), ('n', False), ('y', True),
    ('yes', True), ('YES', True), ('sure', False), (' y ', False)])
def test_remove_requires_explicit_confirmation(vault, answer, removed):
    password, key, config, paths = vault
    source = paths.home.parent / 'source.txt'
    source.write_text('remove only with confirmation')
    manifest = storage.load_manifest(paths, key, config)
    storage.store_file(paths, key, config, manifest, source)
    before = vault_snapshot(paths)
    result, output, _ = drive(ROUTE + ['remove source.txt', answer, 'exit'], [password])
    assert result == 0
    assert "remove 'source.txt'? [y/N]" in output
    assert bool(storage.load_manifest(paths, key, config).entries) != removed
    if not removed:
        assert 'remove: canceled' in output
        assert vault_snapshot(paths) == before


def test_timeout_during_remove_confirmation_preserves_file(vault, sessions):
    password, key, config, paths = vault
    source = paths.home.parent / 'source.txt'
    source.write_text('keep after timeout')
    manifest = storage.load_manifest(paths, key, config)
    storage.store_file(paths, key, config, manifest, source)
    before = vault_snapshot(paths)
    def expire(command):
        if command == 'yes':
            sessions[0].lock()
            sessions[0].timed_out.set()
    result, output, _ = drive(ROUTE + ['remove source.txt', 'yes', 'status'],
                              [password], input_hook=expire)
    assert result == 0
    assert vault_snapshot(paths) == before
    assert 'remove: complete' not in output
    assert 'session: locked (idle timeout)' in output
    assert 'relay0: carrier detected' in output.rsplit('session: locked (idle timeout)', 1)[1]


@pytest.mark.parametrize('stage', ['game', 'password', 'vault', 'confirmation'])
@pytest.mark.parametrize('interrupt', [EOFError, KeyboardInterrupt])
def test_interrupt_cleanup(vault, sessions, stage, interrupt):
    password, _, _, _ = vault
    class TTY(io.StringIO):
        def isatty(self):
            return True
    output = TTY()
    delays = []
    terminal = Terminal(output, effects=True, sleep=delays.append)
    if stage == 'game':
        commands, passwords = [interrupt()], []
    elif stage == 'password':
        commands, passwords = ROUTE, [interrupt()]
    elif stage == 'vault':
        commands, passwords = ROUTE + [interrupt()], [password]
    else:
        commands, passwords = ROUTE + ['remove absent', interrupt()], [password]
    result, output, _ = drive(commands, passwords, terminal=terminal)
    assert result == 0
    assert '\x1b[0m\x1b[?25h' in output
    assert output.rfind('\x1b[?25h') > output.rfind('\x1b[?25l')
    assert all(session.is_locked() for session in sessions)
    assert all(session._key is None and session._manifest is None for session in sessions)
    assert all(session._thread is None for session in sessions)
    assert 'Traceback' not in output


def test_unexpected_error_locks_session_and_hides_details(vault, sessions, monkeypatch):
    password, _, _, _ = vault
    def fail(*args):
        raise RuntimeError('DO-NOT-LEAK-INTERNAL-DETAILS')
    monkeypatch.setattr(VaultSession, 'list_files', fail)
    result, output, _ = drive(ROUTE + ['list'], [password])
    assert result == 1
    assert 'relay0: failure' in output
    assert 'DO-NOT-LEAK' not in output and 'Traceback' not in output
    assert sessions[0].is_locked()
    assert sessions[0]._thread is None


def test_watchdog_start_failure_locks_authenticated_session(vault, sessions, monkeypatch):
    password, _, _, _ = vault
    def fail(*args):
        raise RuntimeError('cannot start watchdog')
    monkeypatch.setattr(VaultSession, 'start_auto_lock', fail)
    result, output, _ = drive(ROUTE, [password])
    assert result == 1
    assert sessions[0].is_locked()
    assert sessions[0]._key is None and sessions[0]._manifest is None
    assert 'cannot start watchdog' not in output


@pytest.mark.parametrize('kind', ['storage', 'io', 'integrity', 'locked'])
def test_operation_errors_use_safe_messages_and_cleanup(vault, sessions, monkeypatch, kind):
    from v2_reference.vault.session import VaultLockedError
    password, _, _, _ = vault
    errors = {'storage': storage.StorageError, 'io': OSError,
              'integrity': crypto.IntegrityError, 'locked': VaultLockedError}
    def fail(*args):
        raise errors[kind]('internal object id and private path')
    monkeypatch.setattr(VaultSession, 'list_files', fail)
    commands = ROUTE + ['list', 'help', 'exit']
    result, output, _ = drive(commands, [password])
    assert result == (1 if kind == 'integrity' else 0)
    assert 'internal object id' not in output
    assert 'Traceback' not in output
    if kind == 'locked':
        assert 'session: locked (idle timeout)' in output
    elif kind in {'storage', 'io'}:
        assert 'show file metadata' in output
    assert sessions[0].is_locked()


def test_shell_looking_input_and_bad_quotes_are_inert(vault):
    password, _, _, paths = vault
    before = vault_snapshot(paths)
    commands = ['"bad', 'help', ''] + ROUTE + [
        '"bad', '', 'shutdown now', 'list | cat', 'list > /etc/passwd',
        '$(reboot)', 'open "red; reboot"', 'help', 'clear', 'exit']
    result, output, _ = drive(commands, [password])
    assert result == 0
    assert output.count('command: invalid quoting') == 2
    assert 'command: unavailable' in output
    assert vault_snapshot(paths) == before
    assert '\x1b' not in output
    assert password not in output


def test_list_info_do_not_expose_object_ids(vault):
    password, key, config, paths = vault
    source = paths.home.parent / 'source.txt'
    source.write_text('safe metadata')
    manifest = storage.load_manifest(paths, key, config)
    entry = storage.store_file(paths, key, config, manifest, source)
    result, output, _ = drive(ROUTE + ['list', 'info source.txt', 'exit'], [password])
    assert result == 0
    assert entry.name in output and str(entry.size) in output
    assert entry.created_at in output and entry.updated_at in output
    assert entry.id not in output
    assert str(paths.objects_dir) not in output
    assert password not in output


@pytest.mark.parametrize('module_route', [False, True])
def test_shared_entrypoint_starts_game_without_authentication(vault, monkeypatch, capsys,
                                                             module_route):
    import builtins
    import runpy
    import sys
    def eof(*args):
        raise EOFError
    def forbidden(*args):
        pytest.fail('No password prompt before gate')
    monkeypatch.setattr(builtins, 'input', eof)
    monkeypatch.setattr(app.getpass, 'getpass', forbidden)
    if module_route:
        monkeypatch.setattr(sys, 'argv', ['v2_reference'])
        with pytest.raises(SystemExit) as stopped:
            runpy.run_module('v2_reference', run_name='__main__')
        assert stopped.value.code == 0
    else:
        assert app.main([]) == 0
    output = capsys.readouterr().out
    assert 'relay0:/proc/relay>' in output
    assert 'vault      :: initialized' in output
    assert 'auth: identity material required' not in output


def test_manual_lock_resets_all_progress_before_next_input(vault, sessions, monkeypatch):
    password, _, _, _ = vault
    games = []
    original = app.GameEngine
    def game():
        instance = original()
        games.append(instance)
        return instance
    monkeypatch.setattr(app, 'GameEngine', game)
    def inspect(command):
        if command == 'help':
            assert sessions[0].is_locked()
            assert games[0].state.current_level == 'relay_root'
            assert games[0].state.flags == set()
            assert games[0].state.consecutive_unknown_commands == 0
    result, output, visits = drive(ROUTE + ['lock', 'help', 'sealctl unlock'],
                                   [password], input_hook=inspect)
    assert result == 0
    assert len(visits) == 1
    assert 'command: unavailable' in output.rsplit('session: locked', 1)[1]


def test_already_timed_out_session_does_not_prompt_in_vault(vault, sessions, monkeypatch):
    password, _, _, _ = vault
    def expired(session):
        session.lock()
        session.timed_out.set()
    monkeypatch.setattr(VaultSession, 'start_auto_lock', expired)
    result, output, _ = drive(ROUTE + ['status'], [password])
    assert result == 0
    assert 'vault0:/data>' not in output
    assert 'relay0: carrier detected' in output.rsplit('session: locked (idle timeout)', 1)[1]


def test_trap_movement_callbacks_and_returned_level_use_game_api(vault, monkeypatch):
    from v2_reference.traps import TrapResult
    events = []
    original = app.GameEngine
    game = original()
    monkeypatch.setattr(app, 'GameEngine', lambda: game)
    def dispatch(trap_id, terminal, config, paths, **callbacks):
        assert trap_id == 'false_probe'
        callbacks['reset_level']()
        assert 'route_verified' not in game.state.flags
        callbacks['move_backward']()
        assert game.state.current_level == 'device_bus'
        events.append(trap_id)
        return TrapResult(new_level='archive_bus')
    monkeypatch.setattr(app, 'dispatch_trap', dispatch)
    result, output, _ = drive(ROUTE[:4] + ['probe 03', 'status'])
    assert result == 0
    assert events == ['false_probe']
    assert 'archive0:/mnt>' in output
    assert 'white  ro  clean' in output


def test_explicit_os_binding_still_uses_traps_after_fake_effects(vault, monkeypatch):
    from v2_reference import os_actions
    _, _, config, paths = vault
    config.real_os_actions = {'enabled': True, 'allowed_actions': ['shutdown'],
                              'bindings': {'signal_scramble': 'shutdown'}}
    save_config_atomic(paths, config)
    output = io.StringIO()
    calls = []
    monkeypatch.setattr(os_actions, 'perform_os_action',
                        lambda action: calls.append((action, output.getvalue())))
    result, _, _ = drive(['unknown'] * 3,
                         terminal=Terminal(output, effects=False))
    assert result == 0
    assert len(calls) == 1 and calls[0][0] == 'shutdown'
    assert 'relay0: carrier degraded' in calls[0][1]


def test_game_clear_and_non_tty_effects_remain_static(vault, monkeypatch):
    output = io.StringIO()
    terminal = Terminal(output, effects=True, sleep=lambda _: pytest.fail('No real delays'))
    cleared = []
    clear = terminal.clear
    def capture():
        cleared.append(True)
        clear()
    monkeypatch.setattr(terminal, 'clear', capture)
    result, output, _ = drive(['clear', 'status'], terminal=terminal)
    assert result == 0
    assert cleared == [True]
    assert 'relay0: carrier detected' in output
    assert '\x1b' not in output


def test_normal_integration_has_no_low_level_crypto_storage_or_os_dispatch():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(app))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            assert not any('os_actions' in name or 'subprocess' in name
                           or 'cryptography' in name for name in names)
            assert 'cryptography' not in (getattr(node, 'module', '') or '')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {'eval', 'exec', '__import__'}
    # Stage 9 initialization is intentionally still primitive composition.
    for function in tree.body:
        if isinstance(function, ast.FunctionDef) and function.name != '_initialize':
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert not (isinstance(node.func.value, ast.Name)
                                and node.func.value.id in {'crypto', 'storage', 'os'})


def test_untrusted_names_cannot_emit_terminal_controls(vault):
    password, key, config, paths = vault
    source = paths.home.parent / 'source.txt'
    source.write_text('metadata display only')
    name = 'notes\x1b[2J\nforged.txt'
    manifest = storage.load_manifest(paths, key, config)
    storage.store_file(paths, key, config, manifest, source, name)
    destination = paths.home.parent / 'retrieved\x1b[2J\nforged.txt'
    result, output, _ = drive(ROUTE + ['list', f'info "{name}"', f'remove "{name}"',
        'n', f'retrieve "{name}" "{destination}"', 'exit'], [password])
    assert destination.read_bytes() == source.read_bytes()
    assert result == 0
    assert '\x1b' not in output
    assert '\nforged.txt' not in output
    assert '\\x1b' in output and '\\nforged.txt' in output
    assert storage.load_manifest(paths, key, config).entries[0].name == name


def test_v2_dashboard_history_and_success_sequence_before_vault(vault):
    password, _, _, _ = vault
    class TTY(io.StringIO):
        def isatty(self):
            return True
    terminal = Terminal(TTY(), effects=True, sleep=lambda _: None, input_stream=io.StringIO())
    result, output, visits = drive(ROUTE + ['list', 'exit'], [password], terminal=terminal)
    assert result == 0
    assert output.index('interlock') < output.index('relay0:/proc/relay>')
    assert output.index('vault      :: initialized') < output.index('auth: identity material required')
    assert 'session         active' not in visits[0]
    assert output.index('key check       ok') < output.index('manifest        verified')
    assert output.index('manifest        verified') < output.index('archive         decrypted')
    assert output.index('session         active') < output.index('vault0:/data>')
    assert '\x1b[2J' not in output


@pytest.mark.parametrize('failure', [KeyboardInterrupt, RuntimeError])
def test_authentication_animation_failure_clears_owned_session(vault, sessions, failure):
    password, _, _, _ = vault
    terminal = Terminal(io.StringIO(), effects=False)
    def fail(*args):
        raise failure()
    terminal.sequence = fail
    result, output, _ = drive(ROUTE, [password], terminal=terminal)
    assert result == (0 if failure is KeyboardInterrupt else 1)
    assert len(sessions) == 1
    assert sessions[0].is_locked()
    assert sessions[0]._key is None and sessions[0]._manifest is None
    assert sessions[0]._thread is None
    assert 'vault0:/data>' not in output


def test_v2_red_readonly_inspection_and_backtracking(vault):
    result, output, visits = drive(ROUTE[:6] + ['mount red', 'status', 'cat journal',
        'probe journal', 'umount red', 'mount white', 'cat index', 'umount white',
        'back', 'status'])
    assert result == 0 and not visits
    assert 'red: journal unstable' in output
    assert 'mount: remounted ro' in output
    assert 'records: 2' in output
    assert output.count('archive0:/mnt>') == 3
    assert 'route13:/link/null>' in output


def test_dashboard_with_real_encrypted_object_stays_public(vault):
    password, key, config, paths = vault
    source = paths.home.parent / 'PRIVATE-FILENAME.txt'
    source.write_bytes(b'PRIVATE-CONTENT')
    manifest = storage.load_manifest(paths, key, config)
    entry = storage.store_file(paths, key, config, manifest, source)
    result, output, visits = drive(['status'])
    assert result == 0 and not visits
    assert 'objects    :: 01' in output
    assert 'session    :: locked' in output
    for secret in (source.name, 'PRIVATE-CONTENT', password, entry.id, str(paths.home)):
        assert secret not in output
