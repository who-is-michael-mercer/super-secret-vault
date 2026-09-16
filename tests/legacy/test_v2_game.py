"""In-memory V2 navigation and unchanged parser/execution boundaries."""

import ast
import io
from pathlib import Path

import pytest

from v2_reference import game, levels
from v2_reference.game import GameEngine
from v2_reference.parser import parse_command
from v2_reference.terminal import Terminal


# Eleven short commands: a learned route fits ordinary 20–40s typing.
ROUTE = ['connect bus', 'scan', 'route -n', 'probe 13', 'connect 13',
         'mount archive0', 'mount black', 'cat controller', 'connect sealctl',
         'sealctl status', 'sealctl unlock']


def command(engine, line):
    return engine.handle(parse_command(line))


def test_exact_successful_route_and_concise_learned_path():
    engine = GameEngine()
    visited = [engine.current_level().id]
    for line in ROUTE:
        result = command(engine, line)
        assert not result.unknown and result.trap_id is None
        if result.transition_to:
            visited.append(result.transition_to)
    assert visited == ['relay_root', 'device_bus', 'route_table', 'null_link',
                       'archive_bus', 'black_archive', 'seal_controller', 'authentication_gate']
    assert result.authentication_gate
    assert len(ROUTE) <= 12
    assert sum(len(line) + 1 for line in ROUTE) <= 160
    assert engine.current_level().id == 'seal_controller'


@pytest.mark.parametrize('identity,blocked,discovery,flag', [
    ('device_bus', 'route -n', 'scan', 'bus_scanned'),
    ('route_table', 'connect 13', 'probe 13', 'route_verified'),
    ('black_archive', 'connect sealctl', 'cat controller', 'controller_found'),
    ('seal_controller', 'sealctl unlock', 'sealctl status', 'seal_ready'),
])
def test_state_gates_cannot_fall_through_to_traps(identity, blocked, discovery, flag):
    engine = GameEngine()
    engine.transition(identity)
    result = command(engine, blocked)
    assert result.unknown and result.trap_id is None and not result.authentication_gate
    assert not result.transition_to
    command(engine, discovery)
    assert flag in engine.state.flags
    result = command(engine, blocked)
    assert result.transition_to and not result.unknown


def test_help_reveals_vocabulary_only_and_hidden_connect_requires_discovery():
    engine = GameEngine()
    engine.transition('route_table')
    assert 'connect' not in engine.available_commands()
    assert '13' not in command(engine, 'help').message
    command(engine, 'probe 13')
    assert 'connect' in engine.available_commands()
    assert 'connect 13' not in command(engine, 'help').message


@pytest.mark.parametrize('identity', levels.LEVELS)
def test_inspection_help_clear_and_backtracking(identity):
    engine = GameEngine()
    engine.transition(identity)
    engine.state.flags.update({'route_verified', 'seal_ready'})
    level = engine.current_level()
    assert command(engine, 'pwd').message == level.prompt.split(':', 1)[1][:-1]
    assert command(engine, 'status').message
    for name in command(engine, 'ls').message.split():
        assert command(engine, 'cat ' + name).message
    flags = engine.state.flags.copy()
    assert command(engine, 'clear').clear
    assert command(engine, 'help').message.splitlines() == list(engine.available_commands())
    output = io.StringIO()
    engine.render_intro(Terminal(output, effects=False))
    assert level.intro_lines[0] in output.getvalue()
    if level.back_target:
        assert command(engine, 'back').transition_to == level.back_target
        assert engine.state.flags == flags
    else:
        assert engine.move_back().noop


def test_diagnostics_is_optional_and_returns_to_relay():
    engine = GameEngine()
    assert command(engine, 'connect diagnostics').transition_to == 'diagnostics'
    assert 'route13: carrier retained' in command(engine, 'cat relay.log').message
    assert 'external keyring unchanged' in command(engine, 'cat history').message
    assert command(engine, 'back').transition_to == 'relay_root'
    assert not engine.state.flags
    for line in ROUTE:
        result = command(engine, line)
    assert result.authentication_gate


def test_white_archive_isolated_even_with_all_discoveries():
    engine = GameEngine()
    engine.transition('archive_bus')
    assert command(engine, 'mount white').transition_to == 'white_archive'
    engine.state.flags.update({'bus_scanned', 'route_verified', 'controller_found', 'seal_ready'})
    for line in (*ROUTE, 'auth', 'store notes', 'cat /etc/passwd'):
        result = command(engine, line)
        assert not result.authentication_gate and not result.transition_to and not result.trap_id
        assert engine.current_level().id == 'white_archive'
    assert command(engine, 'cat index').message == 'readme     current\ninventory  current\nrecords: 2'
    assert command(engine, 'umount white').transition_to == 'archive_bus'


def test_red_inspection_and_risky_write_remain_separate():
    engine = GameEngine()
    engine.transition('archive_bus')
    assert command(engine, 'mount red').transition_to == 'red_maintenance'
    assert 'read-only' in command(engine, 'status').message
    assert command(engine, 'cat journal').trap_id is None
    assert command(engine, 'probe journal').trap_id == 'false_probe'
    assert command(engine, 'mount -o rw red').trap_id == 'red_purge'
    assert engine.current_level().id == 'red_maintenance'
    assert command(engine, 'umount red').transition_to == 'archive_bus'


@pytest.mark.parametrize('identity,line,trap', [
    ('route_table', 'probe 03', 'false_probe'),
    ('route_table', 'probe 08', 'false_probe'),
    ('route_table', 'connect 08', 'false_probe'),
    ('seal_controller', 'sealctl wrong', 'seal_lockout'),
    ('seal_controller', 'sealctl UNLOCK', 'seal_lockout'),
    ('seal_controller', 'sealctl "red; reboot"', 'seal_lockout'),
])
def test_wrong_commands_only_request_traps(identity, line, trap):
    engine = GameEngine()
    engine.transition(identity)
    result = command(engine, line)
    assert result.trap_id == trap and not result.authentication_gate
    assert engine.current_level().id == identity
    assert engine.state.flags == set()


def test_local_reset_and_backtracking_discoveries():
    engine = GameEngine()
    for line in ROUTE[:-1]:
        command(engine, line)
    flags = engine.state.flags.copy()
    command(engine, 'back')
    command(engine, 'connect sealctl')
    assert command(engine, 'sealctl unlock').authentication_gate
    engine.reset_current_level()
    assert engine.state.flags == flags - {'seal_ready'}
    assert command(engine, 'sealctl unlock').unknown
    engine.transition('route_table')
    engine.reset_current_level()
    assert 'route_verified' not in engine.state.flags
    assert command(engine, 'connect 13').unknown


@pytest.mark.parametrize('identity', levels.LEVELS)
def test_unknown_counter_empty_input_and_recognized_reset(identity):
    engine = GameEngine()
    engine.transition(identity)
    for count in (1, 2):
        assert command(engine, 'unknown').unknown
        assert engine.state.consecutive_unknown_commands == count
    assert command(engine, '   ').noop
    assert engine.state.consecutive_unknown_commands == 2
    result = command(engine, 'unknown')
    assert result.trap_id == ('signal_scramble' if identity == 'relay_root' else None)
    assert command(engine, 'status').message
    assert engine.state.consecutive_unknown_commands == 0


@pytest.mark.parametrize('line', ['connect bus extra', 'help extra', 'clear extra', 'back', 'connect BUS'])
def test_invalid_argument_tuples_are_unknown(line):
    engine = GameEngine()
    assert command(engine, line).unknown
    assert engine.current_level().id == 'relay_root'


def test_parser_only_normalizes_command_case():
    engine = GameEngine()
    assert command(engine, 'CONNECT bus').transition_to == 'device_bus'
    command(engine, 'SCAN')
    assert command(engine, 'ROUTE -N').unknown
    assert command(engine, 'ROUTE -n').transition_to == 'route_table'


def test_fresh_instances_and_reset_never_persist_progress(tmp_path, monkeypatch):
    monkeypatch.setenv('VAULTGAME_HOME', str(tmp_path))
    (tmp_path / 'state.json').write_text('not game state')
    engine = GameEngine()
    for line in ROUTE:
        command(engine, line)
    assert engine.state.flags
    assert GameEngine().state.flags == set()
    engine.reset_game()
    assert engine.state == GameEngine().state
    assert engine.current_level().id == 'relay_root'
    assert (tmp_path / 'state.json').read_text() == 'not game state'
    assert len(list(tmp_path.iterdir())) == 1


def test_invalid_direct_transition_preserves_state():
    engine = GameEngine()
    command(engine, 'unknown')
    with pytest.raises(ValueError, match='Unknown level'):
        engine.transition('missing')
    assert engine.current_level().id == 'relay_root'
    assert engine.state.consecutive_unknown_commands == 1


@pytest.mark.parametrize("line", [
    'probe "$(shutdown now)"',
    'probe "red; reboot"',
    'probe "foo | cat /etc/passwd"',
    "probe 13 > output.txt",
    "probe $HOME",
])
def test_shell_looking_arguments_are_inert_unknown_commands(line, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = GameEngine()
    engine.transition("route_table")
    result = command(engine, line)
    assert result.unknown
    assert result.trap_id is None
    assert result.transition_to is None
    assert engine.state.flags == set()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("module,allowed_imports", [
    (game, {"dataclasses", "levels", "parser"}),
    (levels, {"dataclasses"}),
])
def test_game_layer_has_no_execution_persistence_or_later_stage_imports(module, allowed_imports):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "open", "__import__", "compile"}
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"system", "popen", "sleep", "write_text", "write_bytes"}
    assert imports == allowed_imports


@pytest.mark.parametrize('identity,discovery,before,after', [
    ('device_bus', 'scan', 'enumeration pending', 'enumerated'),
    ('route_table', 'probe 13', 'unverified', 'route13: verified'),
    ('black_archive', 'cat controller', 'detached', 'available'),
    ('seal_controller', 'sealctl status', 'unverified', 'control: verified'),
])
def test_status_tracks_local_discovery_and_reset(identity, discovery, before, after):
    engine = GameEngine()
    engine.transition(identity)
    assert before in command(engine, 'status').message
    command(engine, discovery)
    assert after in command(engine, 'status').message
    engine.reset_current_level()
    assert before in command(engine, 'status').message
