import ast
import inspect
from pathlib import Path
import subprocess

import pytest


@pytest.fixture(autouse=True)
def forbid_real_processes(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("OS-action tests must never invoke a real process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


@pytest.mark.parametrize("name", ["close_terminal", "logout", "reboot", "shutdown"])
def test_dispatches_only_predefined_actions(monkeypatch, name):
    from v2_reference import os_actions
    calls = []
    for candidate in ("close_terminal", "logout", "reboot", "shutdown"):
        monkeypatch.setattr(os_actions, candidate, lambda candidate=candidate: calls.append(candidate))
    os_actions.perform_os_action(name)
    assert calls == [name]


@pytest.mark.parametrize("name, command", [
    ("logout", ["/usr/bin/loginctl", "--no-ask-password", "terminate-session", ""]),
    ("reboot", ["/usr/bin/systemctl", "--no-ask-password", "reboot"]),
    ("shutdown", ["/usr/bin/systemctl", "--no-ask-password", "poweroff"]),
])
def test_linux_actions_use_fixed_commands(monkeypatch, name, command):
    from v2_reference import os_actions
    monkeypatch.setattr(os_actions.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_ID", "untrusted; shutdown now")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    getattr(os_actions, name)()
    assert calls == [((command,), {
        "check": True, "shell": False, "timeout": 10,
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
    })]


@pytest.mark.parametrize("failure, error_name", [
    (FileNotFoundError("missing executable"), "UnsupportedActionError"),
    (PermissionError("denied"), "ActionNotAllowedError"),
    (OSError("system unavailable"), "ActionNotAllowedError"),
    (subprocess.CalledProcessError(1, "mocked"), "ActionNotAllowedError"),
    (subprocess.TimeoutExpired("mocked", 10), "ActionNotAllowedError"),
])
def test_execution_errors_are_controlled(monkeypatch, failure, error_name):
    from v2_reference import os_actions
    monkeypatch.setattr(os_actions.sys, "platform", "linux")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(getattr(os_actions, error_name)) as raised:
        os_actions.reboot()
    assert raised.value.__cause__ is failure


@pytest.mark.parametrize("name", ["", "SHUTDOWN", "poweroff", "shutdown now", "$(reboot)",
                                  "reboot;shutdown", "/usr/bin/reboot", None, [], 1])
def test_unknown_action_never_invokes_a_process(name):
    from v2_reference import os_actions
    with pytest.raises(os_actions.UnsupportedActionError):
        os_actions.perform_os_action(name)


@pytest.mark.parametrize("platform", ["win32", "darwin", "freebsd14", "unknown"])
@pytest.mark.parametrize("name", ["close_terminal", "logout", "reboot", "shutdown"])
def test_unsupported_platforms_are_controlled(monkeypatch, platform, name):
    from v2_reference import os_actions
    monkeypatch.setattr(os_actions.sys, "platform", platform)
    with pytest.raises(os_actions.UnsupportedActionError):
        os_actions.perform_os_action(name)


@pytest.fixture
def direct_kitty(monkeypatch):
    from v2_reference import os_actions
    monkeypatch.setattr(os_actions.sys, "platform", "linux")
    for key in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "TMUX", "STY",
                "KITTY_LISTEN_ON", "KITTY_RC_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TERM", "xterm-kitty")
    monkeypatch.setenv("KITTY_WINDOW_ID", "13")
    monkeypatch.setattr(os_actions.os, "isatty", lambda fd: True)
    monkeypatch.setattr(os_actions.os, "ttyname", lambda fd: "/dev/pts/13")
    return os_actions


def test_close_only_identified_current_kitty_window(monkeypatch, direct_kitty):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    direct_kitty.close_terminal()
    assert calls == [((["/usr/bin/kitten", "@", "close-window", "--self"],), {
        "check": True, "shell": False, "timeout": 10,
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
    })]


@pytest.mark.parametrize("key, value", [
    ("TERM", "xterm"), ("KITTY_WINDOW_ID", ""), ("KITTY_WINDOW_ID", "13;reboot"),
    ("KITTY_WINDOW_ID", "１３"), ("SSH_CONNECTION", "remote"), ("SSH_CLIENT", "remote"),
    ("SSH_TTY", "/dev/pts/1"), ("TMUX", "socket"), ("STY", "screen"),
    ("KITTY_LISTEN_ON", "unix:/tmp/elsewhere"), ("KITTY_RC_PASSWORD", "fictional-test-password"),
])
def test_close_rejects_unidentified_or_redirected_sessions(monkeypatch, direct_kitty, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(direct_kitty.UnsupportedActionError):
        direct_kitty.close_terminal()


@pytest.mark.parametrize("fd", [0, 1])
def test_close_requires_direct_tty_input_and_output(monkeypatch, direct_kitty, fd):
    monkeypatch.setattr(direct_kitty.os, "isatty", lambda candidate: candidate != fd)
    with pytest.raises(direct_kitty.UnsupportedActionError):
        direct_kitty.close_terminal()


def test_close_rejects_mismatched_ttys(monkeypatch, direct_kitty):
    monkeypatch.setattr(direct_kitty.os, "ttyname", lambda fd: f"/dev/pts/{fd}")
    with pytest.raises(direct_kitty.UnsupportedActionError):
        direct_kitty.close_terminal()


def test_close_handles_unidentifiable_tty(monkeypatch, direct_kitty):
    def fail(fd):
        raise OSError("no controlling terminal")

    monkeypatch.setattr(direct_kitty.os, "ttyname", fail)
    with pytest.raises(direct_kitty.UnsupportedActionError):
        direct_kitty.close_terminal()


def test_os_boundary_uses_no_shell_signals_or_external_arguments():
    from v2_reference import os_actions
    tree = ast.parse(inspect.getsource(os_actions))
    forbidden_calls = {"system", "popen", "eval", "exec", "kill", "killpg", "getppid",
                       "Popen", "call", "check_call", "check_output"}
    native_commands = []
    run_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in forbidden_calls
            if name == "_run_linux":
                native_commands.append(ast.literal_eval(node.args[0]))
            if name == "run":
                run_calls.append(node)
                assert any(keyword.arg == "shell" and ast.literal_eval(keyword.value) is False
                           for keyword in node.keywords)
    assert len(run_calls) == 1
    assert native_commands == [
        ["/usr/bin/kitten", "@", "close-window", "--self"],
        ["/usr/bin/loginctl", "--no-ask-password", "terminate-session", ""],
        ["/usr/bin/systemctl", "--no-ask-password", "reboot"],
        ["/usr/bin/systemctl", "--no-ask-password", "poweroff"],
    ]


def test_only_traps_imports_os_action_boundary():
    from v2_reference import os_actions
    package = Path(os_actions.__file__).parent
    importers = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [alias.name for alias in node.names]
            else:
                continue
            if any("os_actions" in name.split(".") for name in names):
                importers.add(path.relative_to(package).as_posix())
    assert importers == {"traps.py"}
