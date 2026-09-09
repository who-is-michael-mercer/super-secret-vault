import ast
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from vaultgame import traps
from vaultgame.config import (
    AppConfig, ConfigError, load_config, resolve_paths, save_config_atomic, validate_config,
)

from vaultgame.traps import TRAPS, TrapAction, TrapDefinition, TrapResult
from vaultgame.terminal import Terminal


@pytest.fixture(autouse=True)
def forbid_real_processes(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Trap tests must never invoke a real process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def test_fixed_trap_catalog():
    expected = {
        "signal_scramble": [("scramble", None), ("clear", None)],
        "false_probe": [("fake_corruption", None), ("progress", 1), ("reset_level", None)],
        "red_purge": [("countdown", 5), ("fake_file_deletion", None),
                      ("fake_purge", None), ("clear", None), ("exit_program", None)],
        "seal_lockout": [("fake_corruption", None), ("countdown", 10),
                         ("cooldown", 10), ("exit_program", None)],
        "auth_lockout": [("fake_corruption", None), ("countdown", 5),
                         ("cooldown", 30), ("exit_program", None)],
    }
    assert set(TRAPS) == set(expected)
    for trap_id, actions in expected.items():
        assert TRAPS[trap_id] == TrapDefinition(
            trap_id, tuple(TrapAction(kind, value) for kind, value in actions)
        )
    assert TrapResult() == TrapResult(False, None, 0)


class RecordingTerminal:
    def __init__(self):
        self.calls = []

    def scramble_text(self, text):
        self.calls.append(("scramble", text))

    def clear(self):
        self.calls.append(("clear",))

    def fake_system_messages(self, lines):
        self.calls.append(("messages", tuple(lines)))

    def progress(self, label, duration):
        self.calls.append(("progress", label, duration))

    def countdown(self, seconds, prefix=""):
        self.calls.append(("countdown", seconds, prefix))


@pytest.mark.parametrize("trap_id, expected, exits", [
    ("signal_scramble", ["scramble", "clear"], False),
    ("false_probe", ["messages", "progress", "reset"], False),
    ("red_purge", ["countdown", "messages", "messages", "clear"], True),
])
def test_fake_dispatch_order(tmp_path, trap_id, expected, exits):
    terminal = RecordingTerminal()

    def reset():
        terminal.calls.append(("reset",))
        return "mirror_chamber"

    result = traps.dispatch_trap(
        trap_id, terminal, AppConfig(), resolve_paths(tmp_path), reset_level=reset,
    )

    assert [call[0] for call in terminal.calls] == expected
    assert result == TrapResult(exits, "mirror_chamber" if trap_id == "false_probe" else None, 0)
    if trap_id == "false_probe":
        assert terminal.calls[1][2] == 1
    if trap_id == "red_purge":
        assert terminal.calls[0][1] == 5
        assert "INDEX_07.SYS" in str(terminal.calls)
        assert "MIRROR_CACHE.BIN" in str(terminal.calls)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("unknown_action", [False, True])
def test_unknown_trap_or_action_is_controlled(tmp_path, monkeypatch, unknown_action):
    if unknown_action:
        monkeypatch.setitem(TRAPS, "unknown", TrapDefinition("unknown", (TrapAction("reboot"),)))
    terminal = RecordingTerminal()
    with pytest.raises(traps.TrapError, match="Unknown trap|Unknown trap action"):
        traps.dispatch_trap("unknown", terminal, AppConfig(), resolve_paths(tmp_path))
    assert terminal.calls == []


@pytest.mark.parametrize("failure", ["replace", "write", "load"])
def test_cooldown_failure_is_controlled_and_preserves_state(tmp_path, monkeypatch, failure):
    from vaultgame import config
    paths = resolve_paths(tmp_path)
    paths.state_path.write_text("{" if failure == "load" else '{"schema_version": 1}')
    original = paths.state_path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("simulated persistence failure")

    if failure == "replace":
        monkeypatch.setattr(config.os, "replace", fail)
    elif failure == "write":
        monkeypatch.setattr(config.json, "dump", fail)

    with pytest.raises((traps.TrapError, ConfigError)):
        traps.dispatch_trap("seal_lockout", RecordingTerminal(), AppConfig(), paths)
    assert paths.state_path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [paths.state_path]


@pytest.mark.parametrize("settings", [
    {"traps": {"enabled": False, "disabled_traps": []}},
    {"traps": {"disabled_traps": ["red_purge"]}},
    {"traps": {}, "real_os_actions": {"enabled": True, "allowed_actions": ["shutdown"],
                                      "bindings": {"red_purge": "shutdown"}}},
    {"real_os_actions": {}},
])
def test_configuration_round_trip_and_trap_gates(tmp_path, settings, monkeypatch):
    from vaultgame import os_actions
    actions = []
    monkeypatch.setattr(os_actions, "perform_os_action", actions.append)
    paths = resolve_paths(tmp_path)
    app_config = validate_config({"schema_version": 1, **settings})
    save_config_atomic(paths, app_config)
    assert load_config(paths) == app_config
    assert json.loads(paths.config_path.read_text()) == {"schema_version": 1, **settings}
    terminal = RecordingTerminal()
    result = traps.dispatch_trap("red_purge", terminal, app_config, paths)
    disabled = settings.get("traps", {}).get("enabled") is False or "red_purge" in settings.get("traps", {}).get("disabled_traps", [])
    assert result.exit_program is not disabled
    assert bool(terminal.calls) is not disabled
    assert actions == (["shutdown"] if settings.get("real_os_actions", {}).get("enabled") else [])


@pytest.mark.parametrize("trap_id, countdown, duration", [
    ("seal_lockout", 10, 10), ("auth_lockout", 5, 30),
])
def test_cooldown_persisted_and_ordered(tmp_path, monkeypatch, trap_id, countdown, duration):
    paths = resolve_paths(tmp_path)
    paths.state_path.write_text('{"schema_version": 1, "cooldown_until": null}')
    original = paths.state_path.read_bytes()
    terminal = RecordingTerminal()
    instant = datetime(2026, 9, 8, 18, 30, tzinfo=timezone.utc)
    from vaultgame import config
    real_replace = config.os.replace

    def observe_replace(source, destination):
        assert source.parent == destination.parent == paths.home
        assert destination == paths.state_path
        assert paths.state_path.read_bytes() == original
        assert json.loads(source.read_text()) == {
            "schema_version": 1, "cooldown_until": (instant + timedelta(seconds=duration)).isoformat(),
        }
        terminal.calls.append(("save",))
        real_replace(source, destination)

    monkeypatch.setattr(config.os, "replace", observe_replace)
    result = traps.dispatch_trap(trap_id, terminal, AppConfig(), paths, now=lambda: instant)

    assert result == TrapResult(True, None, duration)
    assert [call[0] for call in terminal.calls] == ["messages", "countdown", "save"]
    assert terminal.calls[1][1] == countdown
    saved = json.loads(paths.state_path.read_text())
    assert datetime.fromisoformat(saved["cooldown_until"]) - instant == timedelta(seconds=duration)
    assert saved["schema_version"] == 1
    assert list(tmp_path.iterdir()) == [paths.state_path]


@pytest.mark.parametrize("kind, callback_name, expected_level", [
    ("reset_level", "reset_level", "mirror_chamber"),
    ("move_backward", "move_backward", "archive_junction"),
    ("lock_vault", "lock_vault", None),
    ("fake_shutdown", None, None),
])
@pytest.mark.parametrize("provided", [False, True])
def test_optional_game_actions_and_fake_shutdown(tmp_path, monkeypatch, kind, callback_name, expected_level, provided):
    monkeypatch.setitem(TRAPS, "custom", TrapDefinition("custom", (TrapAction(kind),)))
    terminal = RecordingTerminal()
    calls = []
    callbacks = {}
    if provided:
        for name in ("reset_level", "move_backward", "lock_vault"):
            def callback(name=name):
                calls.append(name)
                return expected_level
            callbacks[name] = callback

    result = traps.dispatch_trap("custom", terminal, AppConfig(), resolve_paths(tmp_path), **callbacks)

    assert calls == ([callback_name] if provided and callback_name else [])
    assert result == TrapResult(new_level=expected_level if provided else None)
    if kind == "fake_shutdown":
        assert "SHUTDOWN" in str(terminal.calls)
    else:
        assert terminal.calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("section", [
    None, [], {"unknown": True}, {"enabled": 0}, {"enabled": "false"},
    {"disabled_traps": "red_purge"}, {"disabled_traps": [1]},
])
def test_malformed_trap_configuration_rejected(tmp_path, section):
    paths = resolve_paths(tmp_path)
    paths.config_path.write_text(json.dumps({"schema_version": 1, "traps": section}))
    original = paths.config_path.read_bytes()
    with pytest.raises(ConfigError):
        load_config(paths)
    if section is not None:
        with pytest.raises(ConfigError):
            save_config_atomic(paths, AppConfig(traps=section))
    assert paths.config_path.read_bytes() == original


@pytest.mark.parametrize("section", [
    None, [], {"unknown": True}, {"enabled": 1}, {"allowed_actions": "shutdown"},
    {"allowed_actions": [False]}, {"bindings": []}, {"bindings": {"red_purge": []}},
])
def test_malformed_inactive_os_configuration_rejected(section):
    with pytest.raises(ConfigError):
        validate_config({"schema_version": 1, "real_os_actions": section})


def test_disabled_trap_has_no_callbacks_clock_or_persistence(tmp_path):
    paths = resolve_paths(tmp_path / "absent")

    def forbidden():
        pytest.fail("Disabled trap invoked a callback or clock")

    for settings in ({"enabled": False}, {"disabled_traps": list(TRAPS)}):
        for trap_id in TRAPS:
            terminal = RecordingTerminal()
            assert traps.dispatch_trap(
                trap_id, terminal, AppConfig(traps=settings), paths,
                reset_level=forbidden, move_backward=forbidden, lock_vault=forbidden, now=forbidden,
            ) == TrapResult()
            assert terminal.calls == []
    assert not paths.home.exists()


def test_disabling_one_trap_leaves_other_traps_enabled(tmp_path):
    terminal = RecordingTerminal()
    assert traps.dispatch_trap(
        "signal_scramble", terminal, AppConfig(traps={"disabled_traps": ["red_purge"]}),
        resolve_paths(tmp_path),
    ) == TrapResult()
    assert [call[0] for call in terminal.calls] == ["scramble", "clear"]


@pytest.mark.parametrize("trap_id", [None, [], ""])
def test_invalid_trap_id_is_controlled_even_if_disabled(tmp_path, trap_id):
    with pytest.raises(traps.TrapError):
        traps.dispatch_trap(trap_id, RecordingTerminal(), AppConfig(traps={"enabled": False}), resolve_paths(tmp_path))


@pytest.mark.parametrize("settings", [{"enabled": "false"}, [], {"disabled_traps": "red_purge"}])
def test_dispatch_rejects_invalid_in_memory_configuration(tmp_path, settings):
    with pytest.raises((ConfigError, traps.TrapError)):
        traps.dispatch_trap("red_purge", RecordingTerminal(), AppConfig(traps=settings), resolve_paths(tmp_path))


@pytest.mark.parametrize("kind", ["countdown", "cooldown", "progress"])
@pytest.mark.parametrize("value", [None, -1, "5", True])
def test_invalid_timing_action_is_controlled(tmp_path, monkeypatch, kind, value):
    monkeypatch.setitem(TRAPS, "custom", TrapDefinition("custom", (TrapAction(kind, value),)))
    terminal = RecordingTerminal()
    with pytest.raises(traps.TrapError):
        traps.dispatch_trap("custom", terminal, AppConfig(), resolve_paths(tmp_path))
    assert terminal.calls == []
    assert list(tmp_path.iterdir()) == []


def test_cooldown_normalizes_aware_clock_to_utc(tmp_path):
    paths = resolve_paths(tmp_path)
    instant = datetime(2026, 9, 8, 13, tzinfo=timezone(timedelta(hours=-5)))
    traps.dispatch_trap("seal_lockout", RecordingTerminal(), AppConfig(), paths, now=lambda: instant)
    assert json.loads(paths.state_path.read_text())["cooldown_until"] == "2026-09-08T18:00:10+00:00"


def test_cooldown_rejects_naive_clock_without_writing(tmp_path):
    with pytest.raises(traps.TrapError):
        traps.dispatch_trap(
            "seal_lockout", RecordingTerminal(), AppConfig(), resolve_paths(tmp_path),
            now=lambda: datetime(2026, 9, 8),
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["fake_file_deletion", "fake_corruption", "fake_purge", "fake_shutdown"])
def test_fake_destructive_actions_have_zero_filesystem_or_process_operations(tmp_path, monkeypatch, kind):
    monkeypatch.setitem(TRAPS, "custom", TrapDefinition("custom", (TrapAction(kind),)))
    paths = resolve_paths(tmp_path)
    stream = io.StringIO()

    def forbidden(*args, **kwargs):
        pytest.fail("Fake presentation attempted a filesystem or process operation")

    with monkeypatch.context() as guard:
        for name in ("unlink", "remove", "rename", "replace", "rmdir", "system", "popen"):
            guard.setattr(os, name, forbidden)
        for name in ("open", "unlink", "write_text", "write_bytes", "iterdir", "glob", "rglob"):
            guard.setattr(Path, name, forbidden)
        guard.setattr(shutil, "rmtree", forbidden)
        for name in ("Popen", "run", "call", "check_call", "check_output"):
            guard.setattr(subprocess, name, forbidden)
        result = traps.dispatch_trap("custom", Terminal(stream, effects=False, sleep=forbidden), AppConfig(), paths)

    assert result == TrapResult()
    assert stream.getvalue().strip()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("trap_id", list(TRAPS))
def test_every_trap_leaves_vault_and_configuration_unchanged(tmp_path, trap_id):
    paths = resolve_paths(tmp_path)
    paths.objects_dir.mkdir(parents=True)
    paths.manifest_path.write_bytes(b"FICTIONAL TEST MANIFEST\x00\xff")
    (paths.objects_dir / "fictional.vlt").write_bytes(b"FICTIONAL TEST OBJECT\x01")
    paths.config_path.write_text('{"schema_version":1}')
    before = {path.relative_to(paths.vault_dir): path.read_bytes() if path.is_file() else None
              for path in paths.vault_dir.rglob("*")}
    config_before = paths.config_path.read_bytes()
    stream = io.StringIO()
    sleeps = []
    traps.dispatch_trap(
        trap_id, Terminal(stream, effects=False, sleep=sleeps.append), AppConfig(), paths,
        now=lambda: datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    after = {path.relative_to(paths.vault_dir): path.read_bytes() if path.is_file() else None
             for path in paths.vault_dir.rglob("*")}
    assert before == after
    assert paths.config_path.read_bytes() == config_before
    assert sleeps == []
    assert "\x1b" not in stream.getvalue()
    assert "fictional.vlt" not in stream.getvalue()
    assert "FICTIONAL TEST" not in stream.getvalue()


@pytest.mark.parametrize("trap_id", list(TRAPS))
@pytest.mark.parametrize("effects, tty", [(False, True), (True, False), (True, True)])
def test_terminal_rendering_uses_only_injected_delays(tmp_path, trap_id, effects, tty):
    class Stream(io.StringIO):
        def isatty(self):
            return tty

    stream = Stream()
    sleeps = []
    traps.dispatch_trap(
        trap_id, Terminal(stream, effects=effects, sleep=sleeps.append), AppConfig(), resolve_paths(tmp_path),
        now=lambda: datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    output = stream.getvalue()
    assert output.strip()
    if effects and tty:
        assert sleeps
        assert all(delay >= 0 for delay in sleeps)
    else:
        assert sleeps == []
        assert "\x1b" not in output


def test_trap_source_keeps_the_stage_boundary():
    source = inspect.getsource(traps)
    tree = ast.parse(source)
    imports = set()
    forbidden_calls = {"eval", "exec", "system", "popen", "Popen", "sleep", "unlink", "remove", "rmtree"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.update([node.module] if node.module else [alias.name for alias in node.names])
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in forbidden_calls
    assert imports <= {"collections.abc", "dataclasses", "datetime", "config", "terminal", "os_actions"}
    assert "\x1b" not in source


def test_stage4_unknown_trap_and_reset_callback_integration(tmp_path):
    from vaultgame.game import GameEngine
    from vaultgame.parser import parse_command
    engine = GameEngine()
    for _ in range(3):
        request = engine.handle(parse_command("unknown"))
    terminal = RecordingTerminal()
    assert request.trap_id == "signal_scramble"
    assert traps.dispatch_trap(request.trap_id, terminal, AppConfig(), resolve_paths(tmp_path)) == TrapResult()
    assert engine.state.consecutive_unknown_commands == 0
    engine.handle(parse_command("wake"))
    engine.handle(parse_command("probe 13"))
    request = engine.handle(parse_command("probe 03"))
    traps.dispatch_trap(
        request.trap_id, terminal, AppConfig(), resolve_paths(tmp_path), reset_level=engine.reset_current_level,
    )
    assert engine.state.current_level == "mirror_chamber"
    assert "null_echo_found" not in engine.state.flags
    assert list(tmp_path.iterdir()) == []


def test_ordered_callbacks_and_exit_are_returned_without_terminating(tmp_path, monkeypatch):
    actions = ("reset_level", "move_backward", "lock_vault", "exit_program", "clear")
    monkeypatch.setitem(TRAPS, "custom", TrapDefinition("custom", tuple(TrapAction(kind) for kind in actions)))
    terminal = RecordingTerminal()

    def reset():
        terminal.calls.append(("reset",))
        return "sealed_archive"

    def back():
        terminal.calls.append(("back",))
        return "archive_junction"

    def lock():
        terminal.calls.append(("lock",))

    result = traps.dispatch_trap(
        "custom", terminal, AppConfig(), resolve_paths(tmp_path), reset_level=reset, move_backward=back, lock_vault=lock,
    )
    assert result == TrapResult(True, "archive_junction", 0)
    assert [call[0] for call in terminal.calls] == ["reset", "back", "lock", "clear"]


@pytest.mark.parametrize("trap_id", list(TRAPS))
@pytest.mark.parametrize("real_settings", [
    None, {}, {"enabled": False, "allowed_actions": ["shutdown"], "bindings": {
        trap_id: "shutdown" for trap_id in TRAPS
    }},
    {"enabled": True, "allowed_actions": [], "bindings": {
        trap_id: "shutdown" for trap_id in TRAPS
    }},
    {"enabled": True, "allowed_actions": ["shutdown"], "bindings": {}},
    {"enabled": True, "allowed_actions": ["reboot"], "bindings": {
        trap_id: "shutdown" for trap_id in TRAPS
    }},
])
def test_real_action_gates_preserve_every_fake_trap(tmp_path, monkeypatch, trap_id, real_settings):
    from vaultgame import os_actions

    def forbidden(*args):
        pytest.fail("Incomplete real-action configuration reached the OS dispatcher")

    monkeypatch.setattr(os_actions, "perform_os_action", forbidden)
    instant = datetime(2026, 9, 9, tzinfo=timezone.utc)
    baseline_terminal = RecordingTerminal()
    baseline_paths = resolve_paths(tmp_path / "baseline")
    baseline = traps.dispatch_trap(
        trap_id, baseline_terminal, AppConfig(), baseline_paths, now=lambda: instant,
    )
    terminal = RecordingTerminal()
    paths = resolve_paths(tmp_path / "gated")
    result = traps.dispatch_trap(
        trap_id, terminal, AppConfig(real_os_actions=real_settings), paths, now=lambda: instant,
    )
    assert result == baseline
    assert terminal.calls == baseline_terminal.calls
    if result.cooldown_seconds:
        assert paths.state_path.read_bytes() == baseline_paths.state_path.read_bytes()


@pytest.mark.parametrize("trap_id", list(TRAPS))
@pytest.mark.parametrize("action", ["close_terminal", "logout", "reboot", "shutdown"])
def test_explicit_binding_dispatches_once_after_complete_fake_sequence(tmp_path, monkeypatch, trap_id, action):
    from vaultgame import os_actions
    paths = resolve_paths(tmp_path / "bound")
    instant = datetime(2026, 9, 9, tzinfo=timezone.utc)
    baseline_terminal = RecordingTerminal()
    baseline = traps.dispatch_trap(
        trap_id, baseline_terminal, AppConfig(), resolve_paths(tmp_path / "baseline"),
        now=lambda: instant,
    )
    terminal = RecordingTerminal()
    calls = []

    def observe(bound_action):
        assert terminal.calls == baseline_terminal.calls
        if baseline.cooldown_seconds:
            assert json.loads(paths.state_path.read_text())["cooldown_until"] == (
                instant + timedelta(seconds=baseline.cooldown_seconds)
            ).isoformat()
        calls.append(bound_action)

    monkeypatch.setattr(os_actions, "perform_os_action", observe)
    result = traps.dispatch_trap(
        trap_id, terminal, AppConfig(real_os_actions={
            "enabled": True, "allowed_actions": [action], "bindings": {trap_id: action},
        }), paths, now=lambda: instant,
    )
    assert result == baseline
    assert calls == [action]


@pytest.mark.parametrize("settings", [{"enabled": False}, {"disabled_traps": list(TRAPS)}])
def test_disabled_traps_never_reach_explicit_os_bindings(tmp_path, monkeypatch, settings):
    from vaultgame import os_actions

    def forbidden(*args):
        pytest.fail("Disabled trap reached OS dispatcher")

    monkeypatch.setattr(os_actions, "perform_os_action", forbidden)
    config = AppConfig(traps=settings, real_os_actions={
        "enabled": True, "allowed_actions": ["shutdown"],
        "bindings": {trap_id: "shutdown" for trap_id in TRAPS},
    })
    for trap_id in TRAPS:
        terminal = RecordingTerminal()
        assert traps.dispatch_trap(trap_id, terminal, config, resolve_paths(tmp_path)) == TrapResult()
        assert terminal.calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("action", ["shutdown now", "$(reboot)", "reboot; shutdown", "${ACTION}",
                                  "/usr/bin/reboot", "SHUTDOWN", "poweroff", ""])
def test_unsupported_binding_is_controlled_after_fake_actions(tmp_path, monkeypatch, action):
    from vaultgame import os_actions
    terminal = RecordingTerminal()
    config = AppConfig(real_os_actions={
        "enabled": True, "allowed_actions": [action], "bindings": {"red_purge": action},
    })

    def forbidden(*args):
        pytest.fail("Unsupported symbol reached OS dispatcher")

    monkeypatch.setattr(os_actions, "perform_os_action", forbidden)
    with pytest.raises(os_actions.UnsupportedActionError):
        traps.dispatch_trap("red_purge", terminal, config, resolve_paths(tmp_path))
    assert [call[0] for call in terminal.calls] == ["countdown", "messages", "messages", "clear"]


@pytest.mark.parametrize("error_name", ["UnsupportedActionError", "ActionNotAllowedError"])
def test_real_action_errors_remain_controlled_and_follow_cooldown(tmp_path, monkeypatch, error_name):
    from vaultgame import os_actions
    paths = resolve_paths(tmp_path)
    terminal = RecordingTerminal()
    failure = getattr(os_actions, error_name)("mocked OS rejection")
    calls = []

    def fail(action):
        calls.append(action)
        assert paths.state_path.exists()
        assert [call[0] for call in terminal.calls] == ["messages", "countdown"]
        raise failure

    monkeypatch.setattr(os_actions, "perform_os_action", fail)
    with pytest.raises(getattr(os_actions, error_name)) as raised:
        traps.dispatch_trap("seal_lockout", terminal, AppConfig(real_os_actions={
            "enabled": True, "allowed_actions": ["logout"], "bindings": {"seal_lockout": "logout"},
        }), paths, now=lambda: datetime(2026, 9, 9, tzinfo=timezone.utc))
    assert raised.value is failure
    assert calls == ["logout"]


def test_failed_fake_cooldown_prevents_real_action(tmp_path, monkeypatch):
    from vaultgame import os_actions

    def forbidden(*args):
        pytest.fail("Failed fake sequence reached OS dispatcher")

    monkeypatch.setattr(os_actions, "perform_os_action", forbidden)
    paths = resolve_paths(tmp_path)
    paths.state_path.write_text("malformed")
    with pytest.raises(traps.TrapError):
        traps.dispatch_trap("auth_lockout", RecordingTerminal(), AppConfig(real_os_actions={
            "enabled": True, "allowed_actions": ["shutdown"], "bindings": {"auth_lockout": "shutdown"},
        }), paths)
    assert paths.state_path.read_text() == "malformed"


def test_unknown_trap_cannot_use_an_explicit_binding(tmp_path, monkeypatch):
    from vaultgame import os_actions

    def forbidden(*args):
        pytest.fail("Unknown trap reached OS dispatcher")

    monkeypatch.setattr(os_actions, "perform_os_action", forbidden)
    terminal = RecordingTerminal()
    with pytest.raises(traps.TrapError):
        traps.dispatch_trap("unknown", terminal, AppConfig(real_os_actions={
            "enabled": True, "allowed_actions": ["reboot"], "bindings": {"unknown": "reboot"},
        }), resolve_paths(tmp_path))
    assert terminal.calls == []


def test_shell_looking_input_and_game_trap_ids_cannot_bypass_gates(tmp_path, monkeypatch):
    from vaultgame import os_actions
    from vaultgame.game import GameEngine
    from vaultgame.parser import parse_command

    def forbidden(*args):
        pytest.fail("Game input reached OS dispatcher without configuration gates")

    monkeypatch.setattr(os_actions, "perform_os_action", forbidden)
    engine = GameEngine()
    for line in ("reboot; shutdown", 'probe "$(shutdown now)"', 'inspect "foo | cat /etc/passwd"'):
        request = engine.handle(parse_command(line))
    assert request.trap_id == "signal_scramble"
    assert traps.dispatch_trap(
        request.trap_id, RecordingTerminal(), AppConfig(), resolve_paths(tmp_path),
    ) == TrapResult()
    assert engine.state.current_level == "dormant_relay"
    assert list(tmp_path.iterdir()) == []
