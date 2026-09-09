"""Exercise fixed game routes using the real internal parser."""

import ast
import io
from pathlib import Path

import pytest

from vaultgame import game, levels
from vaultgame.game import GameEngine
from vaultgame.parser import parse_command
from vaultgame.terminal import Terminal


def command(engine, line):
    return engine.handle(parse_command(line))


def test_exact_successful_route():
    engine = GameEngine()
    assert engine.current_level().id == "dormant_relay"
    assert engine.state.flags == set()
    assert engine.state.consecutive_unknown_commands == 0
    assert command(engine, "status").message == "CARRIER: ASLEEP\nHANDSHAKE: WAKE SEQUENCE ABSENT"
    assert command(engine, "wake").transition_to == "mirror_chamber"
    assert engine.current_level().id == "mirror_chamber"
    assert command(engine, "scan").message == "SOCKETS: 03 08 13\nRESPONSE RULE: LARGEST PRIME\nECHO TYPE: NULL"
    assert command(engine, "probe 13").message == "ENTRY CHANNEL ACCEPTS: ENTER NULL"
    assert engine.state.flags == {"null_echo_found"}
    assert command(engine, "enter null").transition_to == "archive_junction"
    assert engine.current_level().id == "archive_junction"
    assert command(engine, "inspect").message == (
        "WHITE ARCHIVE\nRED ARCHIVE\nBLACK ARCHIVE\n\n"
        "ONLY THE CHAMBER THAT RETURNS NO LIGHT\nKEEPS A TRUTHFUL INDEX."
    )
    assert command(engine, "open black").transition_to == "sealed_archive"
    assert engine.current_level().id == "sealed_archive"
    assert command(engine, "inspect").message == "SEAL: MIRROR\nSTATE: UNREAD"
    assert command(engine, "read seal").message == "THE MIRROR ACCEPTS ONE VERB:\nUNLOCK"
    assert engine.state.flags == {"null_echo_found", "seal_read"}
    result = command(engine, "unlock mirror")
    assert result.authentication_gate
    assert result.transition_to == "authentication_gate"
    assert result.trap_id is None
    assert engine.current_level().id == "sealed_archive"


@pytest.mark.parametrize(
    "level_id,hidden,discovery,flag",
    [
        ("mirror_chamber", "enter", "probe 13", "null_echo_found"),
        ("sealed_archive", "unlock", "read seal", "seal_read"),
    ],
)
def test_help_reveals_hidden_commands_only_after_discovery(level_id, hidden, discovery, flag):
    engine = GameEngine()
    engine.transition(level_id)
    assert engine.available_commands() == engine.current_level().visible_commands
    assert command(engine, "help").message.splitlines() == list(engine.available_commands())
    assert hidden not in command(engine, "help").message.splitlines()
    command(engine, discovery)
    assert flag in engine.state.flags
    assert engine.available_commands() == (*engine.current_level().visible_commands, hidden)
    assert command(engine, "help").message.splitlines() == list(engine.available_commands())


def test_unknown_counter_and_signal_scramble_threshold():
    engine = GameEngine()
    for count in (1, 2):
        result = command(engine, "nonsense")
        assert result.unknown
        assert result.trap_id is None
        assert engine.state.consecutive_unknown_commands == count
    result = command(engine, "nonsense")
    assert result.unknown
    assert result.trap_id == "signal_scramble"
    assert engine.state.consecutive_unknown_commands == 0
    assert engine.current_level().id == "dormant_relay"
    assert engine.state.flags == set()
    command(engine, "nonsense")
    assert engine.state.consecutive_unknown_commands == 1
    assert not command(engine, "status").unknown
    assert engine.state.consecutive_unknown_commands == 0


@pytest.mark.parametrize("level_id,target", [
    ("mirror_chamber", "dormant_relay"),
    ("archive_junction", "mirror_chamber"),
    ("decoy_archive", "archive_junction"),
    ("sealed_archive", "archive_junction"),
])
def test_back_navigation_preserves_flags(level_id, target):
    engine = GameEngine()
    engine.transition("mirror_chamber")
    command(engine, "probe 13")
    engine.transition("sealed_archive")
    command(engine, "read seal")
    engine.transition(level_id)
    command(engine, "nonsense")
    result = command(engine, "back")
    assert result.transition_to == target
    assert engine.current_level().id == target
    assert engine.state.flags == {"null_echo_found", "seal_read"}
    assert engine.state.consecutive_unknown_commands == 0


@pytest.mark.parametrize("line", ["", "   \t\n"])
def test_empty_input_is_a_noop_and_keeps_counter(line):
    engine = GameEngine()
    command(engine, "nonsense")
    result = command(engine, line)
    assert result.noop
    assert not result.unknown
    assert result.trap_id is None
    assert engine.state.consecutive_unknown_commands == 1


@pytest.mark.parametrize("read_first", [False, True])
@pytest.mark.parametrize("line", ["unlock wrong", "unlock MIRROR", 'unlock "red; reboot"', "unlock mirror extra"])
def test_wrong_unlock_arguments_request_only_seal_lockout(read_first, line):
    engine = GameEngine()
    engine.transition("sealed_archive")
    if read_first:
        command(engine, "read seal")
    command(engine, "nonsense")
    flags = engine.state.flags.copy()
    result = command(engine, line)
    assert result.trap_id == "seal_lockout"
    assert not result.unknown
    assert not result.authentication_gate
    assert result.transition_to is None
    assert engine.current_level().id == "sealed_archive"
    assert engine.state.flags == flags
    assert engine.state.consecutive_unknown_commands == 0


@pytest.mark.parametrize("level_id,remaining", [
    ("mirror_chamber", {"seal_read"}),
    ("sealed_archive", {"null_echo_found"}),
    ("dormant_relay", {"null_echo_found", "seal_read"}),
    ("archive_junction", {"null_echo_found", "seal_read"}),
    ("decoy_archive", {"null_echo_found", "seal_read"}),
])
def test_reset_current_level_removes_only_local_discovery(level_id, remaining):
    engine = GameEngine()
    engine.transition("mirror_chamber")
    command(engine, "probe 13")
    engine.transition("sealed_archive")
    command(engine, "read seal")
    engine.transition(level_id)
    command(engine, "nonsense")
    engine.reset_current_level()
    assert engine.current_level().id == level_id
    assert engine.state.flags == remaining
    assert engine.state.consecutive_unknown_commands == 0
    assert engine.available_commands() == engine.current_level().visible_commands
    if level_id == "mirror_chamber":
        assert command(engine, "enter null").unknown
    if level_id == "sealed_archive":
        assert not command(engine, "unlock mirror").authentication_gate


def test_reset_game_restores_initial_state_and_independent_instances():
    engine = GameEngine()
    other = GameEngine()
    engine.transition("mirror_chamber")
    command(engine, "probe 13")
    engine.transition("sealed_archive")
    command(engine, "read seal")
    command(engine, "nonsense")
    assert other.state.flags == set()
    assert other.state.current_level == "dormant_relay"
    assert other.state.consecutive_unknown_commands == 0
    engine.reset_game()
    assert engine.state == other.state
    assert "wake" not in engine.available_commands()


@pytest.mark.parametrize("level_id", [
    "dormant_relay", "mirror_chamber", "archive_junction", "decoy_archive", "sealed_archive",
])
def test_clear_returns_an_outcome_and_intro_uses_terminal_print(level_id):
    engine = GameEngine()
    engine.transition(level_id)
    stream = io.StringIO()
    terminal = Terminal(stream=stream, effects=False)
    level = engine.current_level()
    engine.render_intro(terminal)
    assert stream.getvalue() == "\n".join((level.ascii_scene, *level.intro_lines, ""))
    command(engine, "nonsense")
    result = command(engine, "clear")
    assert result.clear
    assert not result.unknown
    assert result.message == ""
    assert engine.state.consecutive_unknown_commands == 0
    assert engine.current_level() == level


@pytest.mark.parametrize("level_id,line", [
    ("mirror_chamber", "enter null"),
    ("sealed_archive", "unlock mirror"),
])
def test_required_flags_cannot_be_bypassed_or_fall_through_to_a_trap(level_id, line):
    engine = GameEngine()
    engine.transition(level_id)
    result = command(engine, line)
    assert result.unknown
    assert result.trap_id is None
    assert not result.authentication_gate
    assert result.transition_to is None
    assert engine.state.flags == set()
    assert engine.current_level().id == level_id
    assert engine.state.consecutive_unknown_commands == 1


@pytest.mark.parametrize("level_id,line,trap", [
    ("mirror_chamber", "probe 03", "false_probe"),
    ("mirror_chamber", "probe 08", "false_probe"),
    ("archive_junction", "open red", "red_purge"),
])
def test_wrong_choices_return_trap_ids_without_applying_trap_effects(level_id, line, trap):
    engine = GameEngine()
    engine.transition("mirror_chamber")
    command(engine, "probe 13")
    engine.transition(level_id)
    command(engine, "nonsense")
    result = command(engine, line)
    assert result.trap_id == trap
    assert not result.unknown
    assert not result.authentication_gate
    assert result.transition_to is None
    assert engine.current_level().id == level_id
    assert engine.state.flags == {"null_echo_found"}
    assert engine.state.consecutive_unknown_commands == 0


def test_white_archive_is_a_decoy_and_returns_to_junction():
    engine = GameEngine()
    engine.transition("archive_junction")
    assert command(engine, "open white").transition_to == "decoy_archive"
    assert command(engine, "status").message == "ARCHIVE STATUS: PERFECT\nERROR COUNT: 0\nSECURITY STATE: VERIFIED"
    assert command(engine, "read index").message == "A REAL ARCHIVE WOULD NOT LEAVE THE EXIT OPEN."
    # Even discovery elsewhere cannot turn a decoy command into authentication.
    engine.state.flags.update({"seal_read", "null_echo_found"})
    for line in ("unlock mirror", "enter null", "open black", "read seal", "wake", "store notes", "auth"):
        result = command(engine, line)
        assert result.unknown
        assert not result.authentication_gate
        assert result.transition_to is None
        assert result.trap_id is None
        assert engine.current_level().id == "decoy_archive"
    assert command(engine, "back").transition_to == "archive_junction"


@pytest.mark.parametrize("level_id", [
    "mirror_chamber", "archive_junction", "decoy_archive", "sealed_archive",
])
def test_unknown_threshold_applies_only_at_dormant_relay(level_id):
    engine = GameEngine()
    engine.transition(level_id)
    for count in range(1, 5):
        result = command(engine, "nonsense")
        assert result.unknown
        assert result.trap_id is None
        assert engine.state.consecutive_unknown_commands == count
    command(engine, "help")
    assert engine.state.consecutive_unknown_commands == 0


@pytest.mark.parametrize("line", ["wake extra", "help extra", "clear extra", "back", "WAKE extra"])
def test_unsupported_argument_tuples_and_absent_back_are_unknown(line):
    engine = GameEngine()
    assert command(engine, line).unknown
    assert engine.current_level().id == "dormant_relay"


def test_command_case_is_normalized_only_by_parser_and_argument_case_is_preserved():
    engine = GameEngine()
    assert command(engine, "WAKE").transition_to == "mirror_chamber"
    command(engine, "PROBE 13")
    assert command(engine, "ENTER NULL").unknown
    assert command(engine, "ENTER null").transition_to == "archive_junction"
    assert command(engine, "OPEN BLACK").unknown
    assert command(engine, "OPEN black").transition_to == "sealed_archive"
    assert command(engine, "unlock").unknown


def test_wake_stays_hidden_and_discoveries_survive_backtracking():
    engine = GameEngine()
    assert "wake" not in command(engine, "help").message.splitlines()
    command(engine, "wake")
    command(engine, "probe 13")
    command(engine, "back")
    assert "wake" not in command(engine, "help").message.splitlines()
    command(engine, "wake")
    assert "enter" in engine.available_commands()
    command(engine, "enter null")
    command(engine, "open black")
    command(engine, "read seal")
    command(engine, "back")
    command(engine, "open black")
    assert "unlock" in engine.available_commands()
    assert command(engine, "unlock mirror").authentication_gate


def test_direct_navigation_validates_target_without_corrupting_state():
    engine = GameEngine()
    assert engine.move_back().noop
    command(engine, "nonsense")
    with pytest.raises(ValueError, match="Unknown level"):
        engine.transition("missing")
    assert engine.current_level().id == "dormant_relay"
    assert engine.state.consecutive_unknown_commands == 1
    result = engine.transition("mirror_chamber")
    assert result.transition_to == "mirror_chamber"
    assert engine.state.consecutive_unknown_commands == 0
    assert engine.move_back().transition_to == "dormant_relay"


def test_game_never_reads_or_writes_runtime_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULTGAME_HOME", str(tmp_path))
    # Invalid JSON also establishes that game construction never loads these.
    for name in ("config.json", "state.json"):
        (tmp_path / name).write_text("not game state", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    engine = GameEngine()
    for line in ("wake", "probe 13", "enter null", "open black", "read seal", "unlock mirror"):
        command(engine, line)
    engine.reset_current_level()
    engine.reset_game()
    assert GameEngine().state.flags == set()
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


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
    engine.transition("mirror_chamber")
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
